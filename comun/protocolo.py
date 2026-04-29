"""Definir el protocolo de mensajes que comparten cliente y servidor.

Usar JSON como formato de serialización permite ver fácilmente el contenido
en pantalla durante la presentación y es independiente del lenguaje.
Para TCP, enmarcar los mensajes con un prefijo de longitud (4 bytes);
para UDP, cada datagrama equivale exactamente a un mensaje.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

from comun.configuracion import LONGITUD_CABECERA_TCP


# Declarar los tipos de mensajes como constantes para evitar errores de tipeo
# al compararlos en otros módulos.
TIPO_REGISTRO = "REGISTRO"
TIPO_BROADCAST = "BROADCAST"
TIPO_PRIVADO = "PRIVADO"
TIPO_LISTA_USUARIOS = "LISTA_USUARIOS"
TIPO_RESPUESTA = "RESPUESTA"
TIPO_NOTIFICACION = "NOTIFICACION"
TIPO_DESCONEXION = "DESCONEXION"


@dataclass
class Mensaje:
    """Representar un mensaje del chat con todos sus metadatos.

    Usar un dataclass permite que la conversión a/desde diccionario sea trivial.
    Todos los campos opcionales tienen valor por defecto para poder construir
    sólo lo que se necesita en cada caso (registro, broadcast, privado, etc.).
    """

    tipo: str
    remitente: str = ""
    destinatario: str = ""
    contenido: str = ""
    # Generar la marca de tiempo en el momento de crear el mensaje, en formato ISO
    marca_tiempo: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    # Para respuestas del servidor, indicar si la operación tuvo éxito
    exito: Optional[bool] = None
    # Campo libre para datos extra (por ejemplo la lista de usuarios)
    datos: Optional[dict] = None

    def a_json_bytes(self) -> bytes:
        """Convertir el mensaje a bytes JSON listos para enviar por la red."""
        return json.dumps(asdict(self), ensure_ascii=False).encode("utf-8")

    @staticmethod
    def desde_json_bytes(datos_crudos: bytes) -> "Mensaje":
        """Reconstruir un mensaje a partir de los bytes JSON recibidos."""
        diccionario = json.loads(datos_crudos.decode("utf-8"))
        return Mensaje(**diccionario)


def empaquetar_tcp(mensaje: Mensaje) -> bytes:
    """Anteponer la longitud al cuerpo del mensaje para el enmarcado TCP."""
    cuerpo = mensaje.a_json_bytes()
    cabecera = len(cuerpo).to_bytes(LONGITUD_CABECERA_TCP, "big")
    return cabecera + cuerpo


def recibir_tcp(socket_conexion) -> Optional[Mensaje]:
    """Leer un mensaje completo desde un socket TCP usando el prefijo de longitud.

    Devolver None cuando la conexión se cerró antes de poder leer un mensaje
    completo; así el llamador sabe que debe terminar el bucle de escucha.
    """
    cabecera = _recibir_exacto(socket_conexion, LONGITUD_CABECERA_TCP)
    if cabecera is None:
        return None
    longitud = int.from_bytes(cabecera, "big")
    cuerpo = _recibir_exacto(socket_conexion, longitud)
    if cuerpo is None:
        return None
    return Mensaje.desde_json_bytes(cuerpo)


def _recibir_exacto(socket_conexion, cantidad: int) -> Optional[bytes]:
    """Garantizar la lectura de exactamente la cantidad de bytes solicitada.

    Necesario porque recv() puede devolver menos bytes de los pedidos en TCP.
    Si la conexión se cierra a mitad de lectura, devolver None.
    """
    bufer = bytearray()
    while len(bufer) < cantidad:
        fragmento = socket_conexion.recv(cantidad - len(bufer))
        if not fragmento:
            return None
        bufer.extend(fragmento)
    return bytes(bufer)
