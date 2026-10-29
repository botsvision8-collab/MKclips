"""Facade compatible para la busqueda combinada de referencias.

La implementacion vive en herramientas_busqueda para que no haya dos copias
que puedan divergir. Se conservan el nombre del modulo y sus funciones.
"""

from herramientas_busqueda.buscar_multiples_referencias import *
from herramientas_busqueda.buscar_multiples_referencias import _main_interactivo


if __name__ == "__main__":
    _main_interactivo()
