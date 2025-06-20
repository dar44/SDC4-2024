#############################################################
#                        LIBRERIAS                          #
#############################################################
import requests
import logging
import socket
import threading
import tkinter as tk
from tablero import *
from destino import Destino
import sqlite3
from taxi import Taxi
import json
from cliente import Cliente 
from confluent_kafka import Producer, Consumer, KafkaException, KafkaError
import sys
from variablesGlobales import FORMATO, HEADER, VER, FILAS, COLUMNAS, IP_API, IP_CTC, IP_REG, DB_PATH
import time
import secrets
import ssl
from cryptography.fernet import Fernet, InvalidToken
import os

logging.basicConfig(filename='auditoriaEC.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
# Función para enviar la matriz de taxis a api_central
def enviar_matriz_a_api_central():
    global matriz
    try:
        # Convertir la matriz a una versión serializable a JSON
        matriz_serializable = [
            [
                [elemento.to_dict() if hasattr(elemento, 'to_dict') else elemento for elemento in columna]
                for columna in fila
            ]
            for fila in matriz
        ]
        
        response = requests.post(urlUPDATE, json={"map": matriz_serializable})
        if response.status_code == 200:
            print("Matriz de taxis actualizada en api_central")
        else:
            print(f"Error al actualizar la matriz en api_central: {response.status_code}")
    except Exception as e:
        print(f"Error al enviar la matriz a api_central: {e}")

#############################################################
#      FUNCIÓN PARA OBTENER LA IP DE LA AUDITORÍA           #
#############################################################
def obtener_ip():
    hostname = socket.gethostname()
    ip_address = socket.gethostbyname(hostname)
    return ip_address

#############################################################
#                   VARIABLES GLOBALES                      #
#############################################################
taxisAutenticados = 0
clientes = []
taxis = []
destinos = []
actualizado = True
IP = IP_API
IP2 = IP_CTC
urlUPDATE = f"http://{IP}:5000/update_map"
urlTRAFFIC = f"http://{IP2}:5001/traffic_status"
traffic_status = ""
cert = 'cert.pem'
KEY_DIR = 'keys'
REG_TOKEN_FILE = 'registry_secret.txt'

def load_registry_token():
    try:
        with open(REG_TOKEN_FILE, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return ''

# Utilidad para reiniciar hilos en caso de fallo
def run_with_recovery(target, *args, **kwargs):
    while True:
        try:
            target(*args, **kwargs)
        except Exception as e:
            logging.error(f"{target.__name__} failed: {e}")
            time.sleep(5)

def load_key(taxi_id):
    path = os.path.join(KEY_DIR, f'key_{taxi_id}.key')
    if not os.path.exists(path):
        key = Fernet.generate_key()
        os.makedirs(KEY_DIR, exist_ok=True)
        with open(path, 'wb') as f:
            f.write(key)
    else:
        with open(path, 'rb') as f:
            key = f.read()
    return key

def encrypt_msg(taxi_id, message: str) -> bytes:
    key = load_key(taxi_id)
    f = Fernet(key)
    return f.encrypt(message.encode(FORMATO))

def decrypt_msg(taxi_id, ciphertext: bytes) -> str:
    key = load_key(taxi_id)
    f = Fernet(key)
    return f.decrypt(ciphertext).decode(FORMATO)

#############################################################
#               FUNCION PARA EL OPENWEATHER                 #
#############################################################
def fetch_traffic_status():
    global traffic_status
    while True:
        try:
            response = requests.get(urlTRAFFIC)
            data = response.json()
            traffic_status = str(data["traffic_status"])
            print(f"Traffic status from EC_CTC: {traffic_status}")
        except Exception as e:
            print(f"Error fetching traffic status: {e}")
        time.sleep(10)  # Actualizar cada 10 segundos
        
#############################################################
#        FUNCIONES PARA EL FUNCIONAMIENTO DEL MAPA          #
#############################################################
def imprimirMapa(tablero, ventana):
    global matriz
    
    # tablero.actualizar_tabla_taxis(taxis)
    # tablero.actualizar_tabla_clientes(clientes)
    tablero.actualizarTablero(matriz)
    ventana.after(200, imprimirMapa, tablero, ventana)

def iniciarMapa():
    global destinos
    ventana = tk.Tk()
    tablero = Tablero(ventana)
    destinos = leer_mapa('EC_locations.json')
    print("Destinos leídos con éxito.")      
    
    addDestino(destinos)
    ventana.after(200, imprimirMapa, tablero, ventana)
    ventana.mainloop()

def eliminarTaxi(id):
    global matriz

    for fila in range(len(matriz)):
        
        for columna in range(len(matriz[0])):
            
            for idx, taxi in enumerate(matriz[fila][columna]):
                
                if taxi.id == id:
                    
                    del matriz[fila][columna][idx]
                    enviar_matriz_a_api_central()
                    return True
                
    return False

def addDestino(destinos):
    global matriz

    for destino in destinos:
        fila = destino.posX
        columna = destino.posY
        if not matriz[fila-1][columna-1]:
            matriz[fila-1][columna-1] = []
        matriz[fila-1][columna-1].append(destino)
    enviar_matriz_a_api_central()



def addTaxi(taxi):
    global matriz

    eliminarTaxi(taxi.id)
    limpiarCliente(taxi)
    
    fila = taxi.posicionX
    columna = taxi.posicionY
    if not matriz[fila-1][columna-1]:
        matriz[fila-1][columna-1] = []
    matriz[fila-1][columna-1].insert(0, taxi)

    enviar_matriz_a_api_central()

def addTaxisAutenticados(taxi):
    addTaxi(taxi)

def addCliente(taxi):
    global matriz

    clienteX = int(taxi.clienteX)
    clienteY = int(taxi.clienteY)

    if clienteX is None or clienteY is None:
        raise ValueError("Coordenadas del cliente no son válidas.")

    cliente = Cliente(id=taxi.clienteId, destino=taxi.destino, posX=clienteX, posY=clienteY, estado=taxi.estado)

    fila = cliente.posX
    columna = cliente.posY
    if not matriz[fila-1][columna-1]:
        matriz[fila-1][columna-1] = []
    matriz[fila-1][columna-1].append(cliente) 

    enviar_matriz_a_api_central() 


def limpiarCliente(taxi):
    global matriz
    fila = taxi.posicionX
    columna = taxi.posicionY

    if fila == taxi.clienteX and columna == taxi.clienteY:
        if matriz[fila-1][columna-1]:
            matriz[fila-1][columna-1] = [elemento for elemento in matriz[fila-1][columna-1] if not (isinstance(elemento, Cliente) and elemento.id == taxi.clienteId)]
            enviar_matriz_a_api_central()


def manejarTaxi(conn, addr):
    connected = True

    while connected:
        try:
            msg_length = conn.recv(HEADER).decode(FORMATO)
            if not msg_length:
                if VER: print(f"[CONEXIÓN CERRADA] {addr} se ha desconectado.")
                
                break
            msg_length = int(msg_length)
            msg = conn.recv(msg_length).decode(FORMATO)
            msg = int(msg)
            print("\n")
            autenticarTaxi(msg)
                    
        except ConnectionResetError:
            if VER: print(f"[CONEXIÓN CERRADA] {addr} se ha desconectado inesperadamente.")
            conn.close()
            break
        except Exception as e:
            if VER: print(f"Error inesperado: {e}")
            conn.close()
            break

#############################################################
#      FUNCIÓN QUE AUTENTICA TAXIS CON LA BASE DE DATOS     #
#############################################################
def autenticarTaxi(taxiID):
    global taxis
    idErroneo = True
    token = secrets.token_hex(16 // 2)

     # Comprobar si el taxi está registrado en EC_Registry
    try:
        headers = {'Authorization': f'Bearer {load_registry_token()}'}
        resp = requests.get(
            f"https://{IP_REG}:5002/is_registered/{taxiID}",
            headers=headers,
            verify=False,
        )
        data = resp.json()
        if resp.status_code != 200 or not data.get("registered"):
            print("Taxi no registrado en Registry")
            logging.info(f"Intento de autenticación de taxi {taxiID} sin registro")
            return
    except Exception as e:
        print(f"Error consultando Registry: {e}")
        logging.info(f"Error consultando Registry para taxi {taxiID}: {e}")
        return
    
    # Conectar a la base de datos
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id, estado, posicionX, posicionY, destino, destinoX, destinoY, ocupado FROM taxis")
    filas = cursor.fetchall()

    for fila in filas:
        ocupado = True if fila[7] == 'True' else False
        if taxiID == fila[0]:
            taxi = Taxi(
                id=fila[0], 
                estado=fila[1], 
                posicionX=fila[2], 
                posicionY=fila[3], 
                destino=fila[4], 
                destinoX=fila[5], 
                destinoY=fila[6], 
                ocupado=ocupado,
                clienteX=0,
                clienteY=0,
                clienteId='-',
                base = 0
            )
            idErroneo = False
            taxis.append(taxi)
            for taxi in taxis:
                addTaxisAutenticados(taxi)
            print(f"El taxi {taxi.id} está autentificado")
    if idErroneo:  
        print("Ese taxi no existe")
    conn.close()
    if idErroneo == False:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # Insertar un nuevo taxi en la tabla taxis2
        cursor.execute('''
            INSERT INTO taxis2 (id, posX, posY, estado, clienteId, token)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (taxi.id, taxi.posicionX, taxi.posicionY, taxi.estado, taxi.clienteId, token))
        
        # Confirmar los cambios
        conn.commit()
        
        # Cerrar la conexión
        conn.close()

#############################################################
#    FUNCIÓN QUE RECIBE COMUNICACIÓN DE CLIENTE POR KAFKA   #
#############################################################
def esperandoCliente():
    clienteActualizado = False
    while True:
        try:
            consumer_conf = {
                'bootstrap.servers': f'{SERVER_K}:{PORT_K}',
                'group.id': 'grupo_consumidor2',
                'auto.offset.reset': 'earliest'
            }
            consumer = Consumer(consumer_conf)
            topicPos = 'posicion'

            consumer.subscribe([topicPos])

            while True:
                msg = consumer.poll(1.0)
                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        print(f'Error while receiving message: {msg.error()}')
                        break

                mensaje = msg.value().decode(FORMATO)
                if mensaje == "END":
                    print("El cliente ya no tiene mas servicios")
                    consumer.close()
                    break

                clienteData = mensaje.split(':')
                nuevoCliente = Cliente(
                    id=clienteData[0],
                    destino=clienteData[1],
                    posX=clienteData[2],
                    posY=clienteData[3],
                    estado=clienteData[4],
                )

                print("\n", "He recibido el cliente", nuevoCliente.id, "\n")

                clienteActualizado = False
                for cliente in clientes:
                    if cliente.id == nuevoCliente.id:
                        cliente.destino = nuevoCliente.destino
                        cliente.posX = nuevoCliente.posX
                        cliente.posY = nuevoCliente.posY
                        cliente.estado = "Sin Taxi"
                        clienteActualizado = True

                        conn = sqlite3.connect(DB_PATH)
                        cursor = conn.cursor()
                        cursor.execute('''
                            UPDATE clientes
                            SET posX = ?, posY = ?, estado = ?
                            WHERE id = ?
                        ''', (nuevoCliente.posX, nuevoCliente.posY,
                              nuevoCliente.estado, nuevoCliente.id))
                        conn.commit()
                        conn.close()

                        asignarTaxi(cliente)
                        break

                if not clienteActualizado:
                    clientes.append(nuevoCliente)

                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO clientes (id, posX, posY, estado)
                        VALUES (?, ?, ?, ?)
                    ''', (nuevoCliente.id, nuevoCliente.posX,
                          nuevoCliente.posY, nuevoCliente.estado))
                    conn.commit()
                    conn.close()

                    asignarTaxi(nuevoCliente)

                enviar_matriz_a_api_central()

                print("Lista de clientes:")
                for cliente in clientes:
                    print(cliente)
                break

        except Exception as e:
            logging.error(f"Error en esperandoCliente: {e}")
            time.sleep(5)
           
#############################################################
#          FUNCIÓN QUE ASIGNA CLIENTE AL TAXI               #
#############################################################
def asignarTaxi(cliente):
    global taxis
    taxiOcupados = 0
    for taxi in taxis:
        #print(taxi)
        if taxi.ocupado == False and cliente.estado == "Sin Taxi":
            taxi.ocupado = True
            taxi.estado = "ok"
            taxi.destino = cliente.destino.lower()
            cliente.estado = "Taxi " + str(taxi.id)
            taxi.clienteX = cliente.posX
            taxi.clienteY = cliente.posY
            taxi.clienteId = cliente.id
            #if TodosBase == True:
            if traffic_status == "KO":
                taxi.base = 1
            else :
                taxi.base = 0
            addCliente(taxi)
            #print(cliente)
            print(f"Taxi {taxi.id} asignado a cliente: {taxi.clienteId}") 
            print("Comienza el servicio" , "\n")
            modificarDestinoTaxi()  
           
            moverTaxi(taxi)
            break
        else:
            taxiOcupados += 1
            
    if taxiOcupados == len(taxis):
        print("NO HAY TAXIS DISPONIBLES")
        taxiVacio = None
        avisarCliente(taxiVacio, cliente.id)

#############################################################
#       FUNCIÓN QUE MODIFICA LOS DESTINOS DEL TAXI          #
#############################################################
def modificarDestinoTaxi():
    global taxis
    for destino in destinos:
        letraMin = destino.id.lower()
        for taxi in taxis:
            if letraMin == taxi.destino:
                taxi.destinoX = destino.posX
                taxi.destinoY = destino.posY
                print("Nueva posición del taxi: ", taxi.id, "recibida" , "\n")
                break

#############################################################
#                   FUNCION COMPROBAR                       #
#############################################################
def comprobacion(error, msg):
    if error is not None:
        if VER: print(f'La entrega del mensaje falló: {error}')
    else:
        pass

def obtenerTokenTaxi(taxi_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT token FROM taxis2 WHERE id = ?", (taxi_id,))
    token = cursor.fetchone()
    conn.close()
    return token[0] if token else None

def generarGuardarToken(taxi_id):
    token = secrets.token_hex(16 // 2)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE taxis2 SET token = ? WHERE id = ?", (token, taxi_id))
    conn.commit()
    conn.close()
    return token

#############################################################
#      FUNCIÓN QUE ENVÍA COMUNICACIÓN A ENGINE POR KAFKA    #
#############################################################
def moverTaxi(taxi):
    global traffic_status

    print("Trafic status: ", traffic_status)
    print()

    producer_conf = {'bootstrap.servers': f'{SERVER_K}:{PORT_K}'}
    producer = Producer(producer_conf)
    
    topicMovimiento = 'movimiento'
    token = obtenerTokenTaxi(taxi.id)
    
    if token is None:
        print(f"El taxi {taxi.id} no tiene un token asignado, se le generará uno nuevo")
        token = generarGuardarToken(taxi.id)

    
    if traffic_status == "KO":
        taxi.base = 1
        mensaje = f"{taxi.imprimirTaxi()} % {token}"
        print("mensaje base")
    else:
        taxi.base = 0
        mensaje = f"{taxi.imprimirTaxi()} % {token}"
        print("mensaje taxi")

    encrypted = encrypt_msg(taxi.id, mensaje)
    producer.produce(topicMovimiento, key=str(taxi.id).encode(), value=encrypted, callback=comprobacion)
    time.sleep(1)
    producer.flush()

    
    recibirMovimientoEngine()

#############################################################
#  FUNCIÓN QUE QUE ESCUCHA INFORMACIÓN DE ENGINE POR KAFKA  #
#############################################################
def recibirMovimientoEngine():
    global taxis
    global traffic_status
    while True:
        try:
            consumer_conf = {
                'bootstrap.servers': f'{SERVER_K}:{PORT_K}',
                'group.id': 'grupo_consumidor',
                'auto.offset.reset': 'earliest'
            }
            consumer = Consumer(consumer_conf)
            topicRecorrido = 'recorrido'

            consumer.subscribe([topicRecorrido])
            while True:
                msg = consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        print(f'Error while receiving message: {msg.error()}')
                        break
                taxi_id = msg.key().decode() if msg.key() else ''
                ciphertext = msg.value()
                try:
                    mensaje_completo = decrypt_msg(taxi_id, ciphertext)
                except (InvalidToken, Exception):
                    print(f"Imposible conectar con Taxi {taxi_id}. Mensajes no comprensibles")
                    logging.info(f"Imposible conectar con Taxi {taxi_id}. Mensajes no comprensibles")
                    continue
                if '%' in mensaje_completo:
                    mensaje, token_recibido = mensaje_completo.split('%')
                    token_recibido = token_recibido.strip()
                else:
                    mensaje = mensaje_completo
                    token_recibido = ''
    
                consumer.close()

                taxiData = mensaje.split(':')
                token_registrado = obtenerTokenTaxi(int(taxiData[0]))
                if token_registrado != token_recibido:
                    print(f"Token inválido para taxi {taxiData[0]}")
                    logging.info(f"Token inválido para taxi {taxiData[0]}")
                    continue
                taxirecibido = Taxi(
                    id=int(taxiData[0]),
                    estado=taxiData[1],
                    posicionX=int(taxiData[2]),
                    posicionY=int(taxiData[3]),
                    destino=taxiData[4],
                    destinoX=int(taxiData[5]),
                    destinoY=int(taxiData[6]),
                    ocupado=taxiData[7],
                    clienteX=int(taxiData[8]),
                    clienteY=int(taxiData[9]),
                    clienteId=taxiData[10],
                    base=taxiData[11]
                )
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE taxis2
                    SET posX = ?, posY = ?, estado = ?, clienteId = ?
                    WHERE id = ?
                ''', (taxirecibido.posicionX, taxirecibido.posicionY, taxirecibido.estado, taxirecibido.clienteId, taxirecibido.id))
                conn.commit()
                conn.close()

                print("Nueva posición del taxi: ", taxirecibido.id, " recibida" , "\n")
                addTaxi(taxirecibido)
                for taxi in taxis:
                    if int(taxi.id) == taxirecibido.id:
                        taxi.ocupado = False if taxirecibido.ocupado == "False" else True
                        taxi.estado = taxirecibido.estado
                        taxi.posicionX = taxirecibido.posicionX
                        taxi.posicionY = taxirecibido.posicionY
                        taxi.destino = taxirecibido.destino
                        taxi.destinoX = taxirecibido.destinoX
                        taxi.destinoY = taxirecibido.destinoY
                        taxi.clienteX = taxirecibido.clienteX
                        taxi.clienteY = taxirecibido.clienteY
                        taxi.clienteId = taxirecibido.clienteId
                        taxi.base = 1 if traffic_status == "KO" else 0
                        if taxi.estado == "END":
                            print("El taxi ", taxi.id, " ha acabado el servicio")
                            avisarCliente(taxi, taxi.clienteId)
                        if taxi.estado == "ENDB":
                            print("El taxi ", taxi.id, " se ha desconectado")
                            borrarToken(taxi.id)
                            avisarCliente(taxi, taxi.clienteId)
                        else:
                            envioMapa()
                break
        except Exception as e:
            logging.error(f"Error en recibirMovimientoEngine: {e}")
            time.sleep(5)        

#############################################################
#      FUNCIÓN QUE ENVÍA COMUNICACIÓN A ENGINE POR KAFKA    #
#############################################################

def borrarToken(id):
    try:
        # Conectar a la base de datos
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Ejecutar la consulta DELETE
        cursor.execute("DELETE FROM taxis2 WHERE id = ?", (id,))
        
        # Confirmar los cambios
        conn.commit()
        
        print(f"Datos del taxi con id {id} borrados de la base de datos taxis2")
    except sqlite3.Error as e:
        print(f"Error al borrar los datos del taxi con id {id}: {e}")
    finally:
        # Cerrar la conexión a la base de datos
        if conn:
            conn.close()

#############################################################
#      FUNCIÓN QUE ENVÍA COMUNICACIÓN A ENGINE POR KAFKA    #
#############################################################
def envioMapa():
    global taxis
    global traffic_status

    """ # Incrementar el contador
    contador += 1

    # Verificar si el contador ha llegado a 10
    if contador == 15:
        enviarTaxisABase()"""

    producer_conf = {'bootstrap.servers': f'{SERVER_K}:{PORT_K}'}
    producer = Producer(producer_conf)
    
    topicMapa = 'mapa'
    print("Envio taxi para que se mueva a la siguiente posición")
    """if TodosBase == True:
        mensaje = imprimirTaxisBase()
    else:
        mensaje = imprimirTaxis()"""
    
    if traffic_status == "KO":
        mensaje = imprimirTaxisBase()
    else:
        mensaje = imprimirTaxis()
    
    for taxi in taxis:
        encrypted = encrypt_msg(taxi.id, mensaje)
        producer.produce(topicMapa, key=str(taxi.id).encode(), value=encrypted, callback=comprobacion)
    time.sleep(1)
    producer.flush()

    
   
    recibirMovimientoEngine()


#############################################################
#      FUNCIÓN QUE ENVÍA LOS TAXIS A LA BASE                #
#############################################################
def enviarTaxisABase():
    global TodosBase

    print("Entro en base")
    TodosBase = True

#############################################################
#                 FUNCIÓN QUE IMPRIME TAXIS                 #
#############################################################
def imprimirTaxis() :
    mensaje = ""
    for taxi in taxis :
        taxi.base = 0
        mensaje += taxi.imprimirTaxi() + "/" 

    mensaje = mensaje[:-1]
    return mensaje

def imprimirTaxisBase() :
    mensaje = ""
    for taxi in taxis :
        taxi.base = 1
        mensaje += taxi.imprimirTaxi() + "/" 

    mensaje = mensaje[:-1]
    return mensaje

#############################################################
#      FUNCIÓN QUE ENVÍA COMUNICACIÓN A CLIENTE POR KAFKA   #
#############################################################
def avisarCliente(taxiEnd, clienteId):
    producer_conf = {'bootstrap.servers': f'{SERVER_K}:{PORT_K}'}
    producer = Producer(producer_conf)        
    ip_address = obtener_ip()

    topicDestino = 'destino'

    if taxiEnd is None:
        mensaje = clienteId + ":No hay taxis disponibles"
        logging.info(f"Se avisa al cliente de que no hay taxis disponibles. IP: {ip_address}")
    elif taxiEnd.estado == "ENDB":
        mensaje = clienteId + ":Taxi desconectado"
        logging.info(f"Se avisa al cliente de que el taxi de ha desconectado. IP: {ip_address}")
    else:
        mensaje = clienteId + ":" + taxiEnd.imprimirTaxi()
    print("Aviso al cliente de que ya ha acabado el servicio")
    logging.info(f"Se avisa al cliente de que ya ha acabado el servicio. IP: {ip_address}")

    producer.produce(topicDestino, key=None, value=mensaje.encode(FORMATO), callback=comprobacion)
    producer.flush()
    time.sleep(1)
    esperandoCliente()
    
#############################################################
#          FUNCIÓN PARA LEER LOCALIZACIONES                 #
#############################################################
def leer_mapa(filename):
    global destinos

     # Conectar a la base de datos
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Crear la tabla destinos
    cursor.execute('DROP TABLE IF EXISTS destinos')
    cursor.execute('''
        CREATE TABLE destinos (
            id TEXT PRIMARY KEY,
            fila INTEGER,
            columna INTEGER
        )
    ''')

    with open(filename, 'r') as file:
        data = json.load(file)
        for location in data["locations"]:
            id = location["Id"]
            fila, columna = map(int, location["POS"].split(','))
            destino = Destino(id, fila, columna)
            destinos.append(destino)

            # Insertar en la base de datos
            cursor.execute('INSERT INTO destinos (id, fila, columna) VALUES (?, ?, ?)', (id, fila, columna))

    # Guardar los cambios y cerrar la conexión
    conn.commit()
    conn.close()
    
    crearTablas()
    
    return destinos


#############################################################
#          FUNCIÓN QUE INICIALIZA LA BASE DE DATOS          #
#############################################################
def crearTablas():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Crear la tabla clientes
    cursor.execute('DROP TABLE IF EXISTS clientes')
    cursor.execute('''
        CREATE TABLE clientes (
            id TEXT PRIMARY KEY,
            posX INTEGER,
            posY INTEGER,
            estado TEXT
        )
    ''')

    # Crear la tabla taxis
    cursor.execute('DROP TABLE IF EXISTS taxis2')
    cursor.execute('''
        CREATE TABLE taxis2 (
            id INTEGER PRIMARY KEY,
            posX INTEGER,
            posY INTEGER,
            estado TEXT,
            clienteId TEXT,
            token TEXT
        )
    ''')

    # Guardar los cambios y cerrar la conexión
    conn.commit()
    conn.close()


#############################################################
#          FUNCIÓN QUE INICIALIZA LA MATRIZ VACIA           #
#############################################################
def matrizVACIA():
    global FILAS
    global COLUMNAS

    return [[[] for _ in range(FILAS)] for _ in range(COLUMNAS)]

matriz = matrizVACIA()

#############################################################
#                         MAIN                              #
#############################################################
if __name__ == "__main__":
    ip_address = obtener_ip()
    if  (len(sys.argv) == 5):
        SERVER = sys.argv[1]      
        PORT_E = int(sys.argv[2]) 
        ADDR = (SERVER, PORT_E)     
        SERVER_K = sys.argv[3] 
        PORT_K = int(sys.argv[4]) 




        destinos = leer_mapa('EC_locations.json')
        addDestino(destinos)


        
        servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(certfile=cert, keyfile=cert)
        servidor = context.wrap_socket(servidor, server_side=True)
        servidor.bind(ADDR)
        

        #map_thread = threading.Thread(target=iniciarMapa)
        #map_thread.start()

        kafka_thread = threading.Thread(target=run_with_recovery, args=(esperandoCliente,))
        kafka_thread.start()
        traffic_thread = threading.Thread(target=run_with_recovery, args=(fetch_traffic_status,))
        traffic_thread.start()

        servidor.listen()
        logging.info(f"Central se encuentra escuchando a los demás componentes del proyecto. IP: {ip_address}")
        print("Escuchando a los demás componentes del proyecto.",  "\n")
        while True:
            #mensaje= fetch_traffic_status()
            conn, addr = servidor.accept()
            thread = threading.Thread(target=manejarTaxi, args=(conn, addr))
            thread.start()

    else:
        print("Necesito estos argumentos: <ServerIP_C> <Puerto_C> <ServerIP_K> <Puerto_K>")
        logging.info(f"ERROR: Se necesitan estos argumentos: <ServerIP_C> <Puerto_C> <ServerIP_K> <Puerto_K>. IP: {ip_address}")
        

