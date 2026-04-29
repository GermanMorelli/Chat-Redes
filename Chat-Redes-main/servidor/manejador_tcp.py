"""Implementar el servidor TCP usando un hilo dedicado por cada cliente.

Seguir el modelo clásico "thread-per-connection" porque la especificación pide
sólo cinco clientes concurrentes, así que el costo de cada hilo es asumible
y el código queda mucho más sencillo de explicar.
"""

from __future__ import annotations

import socket
import threading
from typing import Callable

from comun.configuracion import MAXIMO_CLIENTES
from comun.protocolo import (
    Mensaje,
    TIPO_REGISTRO,
    TIPO_RESPUESTA,
    empaquetar_tcp,
    recibir_tcp,
)
from servidor.gestor_usuarios import GestorUsuarios, UsuarioConectado
from servidor.procesador_mensajes import ProcesadorMensajes


class ServidorTCP:
    """Aceptar conexiones TCP y atender a cada cliente en su propio hilo."""

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

    def iniciar(self) -> None:
        """Poner el servidor a escuchar y aceptar clientes hasta que se detenga."""
        self._socket_servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket_servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket_servidor.bind((self._host, self._puerto))
        self._socket_servidor.listen(MAXIMO_CLIENTES)
        self._activo = True
        self._registrar_log(f"[TCP] Escuchando en {self._host}:{self._puerto}")

        try:
            while self._activo:
                socket_cliente, direccion = self._socket_servidor.accept()
                # Lanzar un hilo dedicado para no bloquear las nuevas conexiones
                hilo = threading.Thread(
                    target=self._atender_cliente,
                    args=(socket_cliente, direccion),
                    daemon=True,
                )
                hilo.start()
        except OSError:
            # Al cerrar el socket en detener(), accept() lanza OSError;
            # tratar esto como salida normal del bucle.
            pass

    def detener(self) -> None:
        """Cerrar el socket del servidor para terminar el bucle de aceptación."""
        self._activo = False
        if self._socket_servidor is not None:
            self._socket_servidor.close()

    def _atender_cliente(
        self, socket_cliente: socket.socket, direccion: tuple
    ) -> None:
        """Manejar el ciclo de vida completo de un cliente TCP."""
        nombre_usuario: str | None = None
        try:
            # Exigir que el cliente se registre antes de cualquier otra acción
            mensaje_inicial = recibir_tcp(socket_cliente)
            if mensaje_inicial is None or mensaje_inicial.tipo != TIPO_REGISTRO:
                self._enviar_respuesta_directa(
                    socket_cliente,
                    exito=False,
                    descripcion="Debes enviar un mensaje de registro primero.",
                )
                return

            usuario = UsuarioConectado(
                nombre=mensaje_inicial.remitente,
                direccion=direccion,
                socket_tcp=socket_cliente,
            )
            exito, descripcion = self._gestor.registrar(usuario)
            self._enviar_respuesta_directa(socket_cliente, exito, descripcion)
            if not exito:
                return

            nombre_usuario = usuario.nombre
            self._registrar_log(
                f"[TCP] {nombre_usuario} conectado desde {direccion}"
            )
            self._procesador.notificar_ingreso(nombre_usuario)

            # Escuchar indefinidamente los mensajes del cliente
            while True:
                mensaje = recibir_tcp(socket_cliente)
                if mensaje is None:
                    break
                # Sobrescribir el remitente con el nombre real registrado para
                # evitar que un cliente se haga pasar por otro.
                mensaje.remitente = nombre_usuario
                self._procesador.procesar(mensaje)
        except (ConnectionResetError, OSError):
            # El cliente cerró abruptamente; tratar como desconexión normal
            pass
        finally:
            if nombre_usuario is not None:
                self._gestor.eliminar(nombre_usuario)
                self._procesador.notificar_salida(nombre_usuario)
                self._registrar_log(f"[TCP] {nombre_usuario} desconectado.")
            socket_cliente.close()

    def _enviar_respuesta_directa(
        self, socket_cliente: socket.socket, exito: bool, descripcion: str
    ) -> None:
        """Enviar una respuesta al cliente sin pasar por el gestor de usuarios."""
        respuesta = Mensaje(
            tipo=TIPO_RESPUESTA,
            remitente="Servidor",
            contenido=descripcion,
            exito=exito,
        )
        try:
            socket_cliente.sendall(empaquetar_tcp(respuesta))
        except OSError:
            # No es posible enviar la respuesta; ignorar el error
            pass

    def _enviar_a_usuario(self, usuario: UsuarioConectado, mensaje: Mensaje) -> None:
        """Enviar un mensaje a un usuario específico a través de su socket TCP."""
        if usuario.socket_tcp is None:
            return
        try:
            usuario.socket_tcp.sendall(empaquetar_tcp(mensaje))
        except OSError:
            self._registrar_log(
                f"[TCP] Error al enviar a {usuario.nombre}, lo desconecto."
            )
            self._gestor.eliminar(usuario.nombre)
