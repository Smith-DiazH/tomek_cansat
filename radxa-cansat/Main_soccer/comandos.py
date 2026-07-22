 # comandos.py
DIRECTIONS = {
    'F': (255, 0, 255, 0),   # Adelante:        motorA fwd, motorB fwd
    'B': (255, 1, 255, 1),   # Atrás:           motorA rev, motorB rev
    'L': (120, 1, 120, 0),   # Giro izquierda:  A rev, B fwd (sobre su eje)
    'R': (120, 0, 120, 1),   # Giro derecha:    A fwd, B rev
    'G': (100, 0, 255, 0),   # Adelante-izq:    A lento fwd, B rápido fwd
    'I': (255, 0, 100, 0),   # Adelante-der:    A rápido fwd, B lento fwd
    'H': (100, 1, 255, 1),   # Atrás-izq
    'J': (255, 1, 100, 1),   # Atrás-der
    'S': (0,   0, 0,   0),   # Stop
}
