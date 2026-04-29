"""Implementar el servidor UDP usando un único socket que recibe datagramas.

A diferencia de TCP no hay conexión, así que identificar a cada cliente por
la dirección (host, puerto) desde la que llegó su mensaje de registro.
"""

from __future__ import annotations

import socket
import threading
from typing import Callable

from comun.configuracion import TAMANO_BUFFER_UDP
from comun.protocolo import (
    Mensaje,
    TIPO_DESCONEXION,
    TIPO_REGISTRO,
    TIPO_RESPUESTA,
)
from servidor.gestor_usuarios import GestorUsuarios, UsuarioConectado
from servidor.procesador_mensajes import ProcesadorMensajes


class ServidorUDP:
    """Recibir datagramas UDP en un solo socket y responder según el remitente."""

    def __init__(self, host: str, puerto: int, registrar_log: Callable[[str], None]) -> None:
        self._host = host
        self._puerto = puerto
        self._registrar_log = registrar_log
        self._gestor = GestorUsuarios()
        self._procesador = ProcesadorMensajes(
            self._gestor, self._enviar_a_usuario, registrar_log
        )
        self._socket_servidor: socket.socket | None = None
        self._activo = False
        # Proteger el sendto() porque varios hilos podrían querer enviar a la vez
        self._cerrojo_envio = threading.Lock()

    def iniciar(self) -> None:
        """Iniciar el servidor UDP y procesar datagramas hasta que se detenga."""
        self._socket_servidor = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket_servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket_servidor.bind((self._host, self._puerto))
        self._activo = True
        self._registrar_log(f"[UDP] Escuchando en {self._host}:{self._puerto}")

        while self._activo:
            try:
                datos, direccion = self._socket_servidor.recvfrom(TAMANO_BUFFER_UDP)
            except OSError:
                break
            try:
                mensaje = Mensaje.desde_json_bytes(datos)
            except Exception as error:
                self._registrar_log(
                    f"[UDP] Mensaje inválido desde {direccion}: {error}"
                )
                continue
            self._manejar_datagrama(mensaje, direccion)

    def detener(self) -> None:
        """Cerrar el socket UDP para terminar el bucle de recepción."""
        self._activo = False
        if self._socket_servidor is not None:
            self._socket_servidor.close()

    def _manejar_datagrama(self, mensaje: Mensaje, direccion: tuple) -> None:
        """Decidir qué hacer con un datagrama según su tipo."""
        if mensaje.tipo == TIPO_REGISTRO:
            self._registrar_usuario(mensaje, direccion)
            return
        if mensaje.tipo == TIPO_DESCONEXION:
            self._desconectar_usuario(mensaje.remitente)
            return

        # Procesar sólo si el remitente está registrado
        usuario = self._gestor.obtener(mensaje.remitente)
        if usuario is None:
            return
        # Actualizar la dirección por si el cliente cambió de puerto efímero
        usuario.direccion = direccion
        self._procesador.procesar(mensaje)

    def _registrar_usuario(self, mensaje: Mensaje, direccion: tuple) -> None:
        """Dar de alta a un nuevo usuario y confirmarle el resultado."""
        usuario = UsuarioConectado(nombre=mensaje.remitente, direccion=direccion)
        exito, descripcion = self._gestor.registrar(usuario)
        respuesta = Mensaje(
            tipo=TIPO_RESPUESTA,
            remitente="Servidor",
            destinatario=mensaje.remitente,
            contenido=descripcion,
            exito=exito,
        )
        self._enviar_a_direccion(direccion, respuesta)
        if exito:
            self._registrar_log(
                f"[UDP] {usuario.nombre} conectado desde {direccion}"
            )
            self._procesador.notificar_ingreso(usuario.nombre)

    def _desconectar_usuario(self, nombre: str) -> None:
        """Dar de baja a un usuario que envió un mensaje de desconexión."""
        if self._gestor.eliminar(nombre) is not None:
            self._registrar_log(f"[UDP] {nombre} desconectado.")
            self._procesador.notificar_salida(nombre)

    def _enviar_a_usuario(
        self, usuario: UsuarioConectado, mensaje: Mensaje
    ) -> None:
        """Enviar un mensaje a un usuario UDP usando su dirección guardada."""
        self._enviar_a_direccion(usuario.direccion, mensaje)

    def _enviar_a_direccion(self, direccion: tuple, mensaje: Mensaje) -> None:
        """Enviar bytes UDP a una dirección concreta de forma segura entre hilos."""
        if self._socket_servidor is None:
            return
        with self._cerrojo_envio:
            try:
                self._socket_servidor.sendto(mensaje.a_json_bytes(), direccion)
            except OSError as error:
                self._registrar_log(
                    f"[UDP] Error al enviar a {direccion}: {error}"
                )
