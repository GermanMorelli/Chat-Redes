"""Centralizar las constantes de configuración para no repetirlas en otros módulos."""

# Definir el host y puerto por defecto del servidor para facilitar el cambio
HOST_POR_DEFECTO = "127.0.0.1"
PUERTO_POR_DEFECTO = 5050

# Limitar el número máximo de clientes conectados según pide la especificación
MAXIMO_CLIENTES = 5

# Listar los protocolos válidos que acepta el programa en línea de comandos
PROTOCOLOS_VALIDOS = ("TCP", "UDP")

# Tamaño máximo seguro de un datagrama UDP para usar al llamar recvfrom
TAMANO_BUFFER_UDP = 65507

# Cantidad de bytes reservados para la cabecera de longitud en TCP
LONGITUD_CABECERA_TCP = 4
