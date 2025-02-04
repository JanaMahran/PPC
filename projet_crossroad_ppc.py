from multiprocessing import Process, Value, Array, Lock
import signal
import sysv_ipc
import random
import time
import os
import pickle
import socket
import json
from functools import partial #à remplacer par un lambda maybe


class Vehicle:
    def __init__(self, vehicle_id, source, destination, priority=False):
        self.vehicle_id = vehicle_id
        self.source = source
        self.destination = destination
        self.priority = priority

    def __str__(self):
        return f"/n{'Priority' if self.priority else 'Normal'} Vehicle {self.vehicle_id} from {self.source} to {self.destination}"


def generate_vehicle(vehicle_type, queues):
    """
    Generates a vehicle (serialized object) message with a random source and destination,
    and sends it to the appropriate queue based on its source.
    """
    source = random.choice(directions)
    destination = random.choice([d for d in directions if d != source])  # Avoid same source & destination
    
    vehicle = Vehicle(vehicle_id=random.randint(1000, 9999), source=source, destination=destination, priority=(vehicle_type == priority))
    vehicle_data = pickle.dumps(vehicle)
    
    queues[source].send(vehicle_data, type=vehicle_type)  # Send message to source queue
    print(f"Generated {('Normal' if vehicle_type == normal else 'Priority')} vehicle: {source} -> {destination}")
    #METTRE VEHICULE PRIORITAIRE AU DEBUT DE LA FILE DES QU'IL EST GENERE OU ALORS LE METTRE DANS LA QUEUE TRANQUILLE ET FAIRE BIDOUILLES EN LISANT JUSTE SA FILE JUSQU'A SON TOUR/ EN LE FAISANT AVANCER ET GRUGER PROGRESSIVEMENT


def normal_traffic_gen(queues): 
    """generate vehiculeS at a particular delay"""
    while True :     
        generate_vehicle(normal, queues)
        delai_arrivee_normal = random.uniform(2,4)
        time.sleep(delai_arrivee_normal)  # Normal vehicles are more frequent


def priority_traffic_gen(queues, pid_feux):
    """pid nécessaire pour envoyer le signal au process lights"""
    #GERER LE PROBLEME DE LA VARIABLE GLOBALE POUR DIRE OU EST LE Priority traffic, là ou autre part
    while True :
        source = random.choice(directions)
        priority_state.value = directions.index(source)
        generate_vehicle(priority, queues)
        os.kill(pid_feux, signal.SIGUSR1)  # Envoyer le signal pour que lights soit au courant
        # Priority vehicles are less frequent (cohérent avec la réalité)
        delai_arrivee_prioritaire = random.uniform(6,8)
        #génération des véhicules prioritaire à délai suffisamment grand pour considérer qu'il y a un seul véhicule prioritaire à la fois
        time.sleep(delai_arrivee_prioritaire)


def priority_sig_handler(sig, frame, lights_state, priority_state):
    """fonction qui gère l'arrivée d'un véhicule prioritaire, annoncée par un signal sig 
    la source du véhicule est lue dans la variable en mémoire partagée priority_state
    elle modifie directement la variable en mémoire partagée lights_state pour indiquer
    un changement des feux"""
    if sig == signal.SIGUSR1 :
        with lights_lock:
            direction = priority_state.value #en théorie si on a reçu un signal, la valeur de cette variable ne peut pas être 4
            print(f"Véhicule prioritaire qui arrive de {direction}, faites de la place!")
            # on passe au rouge tous les feux sauf celui de la direction prioritaire
            for i in range(len(lights_state)):
                lights_state[i] = 0
            lights_state[direction] = 1   
        print(f"Nouvel état des feux : {list(lights_state)}")


def lights():
    """fonction qui gère l'alternance des feux et réagit aux véhicules prioritaires"""
    #on utilise partial de sorte à passer lights_state et priority_state en paramètre à priority_sig_handler
    signal.signal(signal.SIGUSR1, partial(priority_sig_handler, lights_state = lights_state, priority_state = priority_state))
    while True:
        if priority_state.value == 4: #mode normal
            # Passage Nord/Sud verts, Est/Ouest rouges
            lights_state[:] = [1, 1, 0, 0]
            print(f"Nord/Sud verts, Est/Ouest rouges : {list(lights_state)}")
            delai_alternance = 4 #choix arbitraire de tous les combien de temps 
            time.sleep(delai_alternance)  # Simulation d'un changement normal des feux
            
            if priority_state.value == 4:  # revérification après le délai
                # Passage Est/Ouest verts, Nord/Sud rouges
                lights_state[:] = [0, 0, 1, 1]
                print(f"Est/Ouest verts, Nord/Sud rouges : {list(lights_state)}")
                time.sleep(delai_alternance)
        
        else: #si non normal, alors prioritaire !
           print("Mode priorité activé, feux adaptés à la situation")
           temps_passage_prioritaire = 3
           time.sleep(temps_passage_prioritaire)  # Petite attente avant de revenir en mode normal
           #COMMENT SAVOIR SI LE VEHICULE EST BIEN PASSE EN CE TEMPS ?
           priority_state.value = 4  # Retour au mode normal après passage du véhicule
    
        #MOYEN QUE LIGHTS VERIFIE AVANT 4 SECONDES SI NOUVEAU VEHICULE PRIORITAIRE ?
    
def create_queues():
    """crée 4 message queues, 1 pour pour chaque direction du carrefour"""
    queues = {}
    for direction, key in sections.items():
        try:
            queues[direction] = sysv_ipc.MessageQueue(key, sysv_ipc.IPC_CREX)  # Create new queue
        except sysv_ipc.ExistentialError:
            queues[direction] = sysv_ipc.MessageQueue(key)  # Attach to existing queue
    return queues

def access_queues():
    """permet d'accéder aux messages queues et de les renvoyer"""
    queues = {}
    for direction, key in directions:
        queues[direction] = sysv_ipc.MessageQueue(key)  # Attach to existing queue
    return queues


def send_to_display(message):
    """fonction d'envoi de messages au processus display
    utilise des sockets"""
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(('localhost', 5000))
    client_socket.send(json.dumps(message).encode('utf-8'))
    client_socket.close()


def coordinator():
    #read les queues pour les véhicules 
    queues = access_queues()
    waiting_vehicles = {direction: None for direction in directions}
    #permet de stocker un véhicule en attente à chaque feu
    #nécessaire car quand on lit queue avec receive on retire le véhicule 
    #si doit attendre pour passer à cause de priorité à droite, le met dans waiting_vehicules
    
    while running:  # on utilise ici la variable globale running pour contrôler la boucle
        for direction, queue in queues.items():
            with queue_locks[direction]:
                if waiting_vehicles[direction] is None:
                    try:
                        message, message_type = queue.receive(block=False)
                        vehicle = pickle.loads(message)
                        print(f"Coordinator: Processing {'Priority' if vehicle.priority else 'Normal'} vehicle from {vehicle.source} to {vehicle.destination}")
                        
                        with lights_lock:
                            if lights_state[directions.index(direction)] == 1:
                                if can_vehicle_pass(vehicle, queues):
                                    print(f"Vehicle {vehicle.vehicle_id} from {vehicle.source} to {vehicle.destination} is passing the intersection.")
                                    move_vehicle(vehicle, queues)
                                    send_to_display({"passing": {direction: 1}})
                                else:
                                    print(f"Vehicle {vehicle.vehicle_id} from {vehicle.source} to {vehicle.destination} is waiting due to priority rules.")
                                    # Stocke donc le véhicule en attente
                                    waiting_vehicles[direction] = (message, message_type)
                                    send_to_display({"waiting": {direction: 1}})
                            else:
                                print(f"Vehicle {vehicle.vehicle_id} from {vehicle.source} to {vehicle.destination} is waiting for green light.")
                                # Stocke le véhicule en attente si le feu est rouge
                                waiting_vehicles[direction] = (message, message_type)
                                send_to_display({"waiting": {direction: 1}})
                    
                    except sysv_ipc.BusyError:
                        continue
                
                else:
                    # Traiter le véhicule en attente pour cette direction
                    message, message_type = waiting_vehicles[direction]
                    vehicle = pickle.loads(message)
                    
                    with lights_lock:
                        if lights_state[directions.index(direction)] == 1:
                            # On vérifie si le véhicule peut maintenant passer
                            if can_vehicle_pass(vehicle, queues):
                                print(f"Vehicle {vehicle.vehicle_id} from {vehicle.source} to {vehicle.destination} is now passing the intersection.")
                                move_vehicle(vehicle, queues)
                                send_to_display({"passing": {direction: 1}})
                                #On peut maintenant retirer le véhicule de la liste d'attente
                                waiting_vehicles[direction] = None
          
      

def can_vehicle_pass(vehicle, queues):
    """
    Détermine si un véhicule peut passer en fonction des règles de priorité. 
    On applique la règle de la priorité à droite pour départager si besoin les véhicules dont le feu est vert.
    """
    for i in range(len(directions)):
        if i != directions.index(vehicle.source) and lights_state[i] == 1:
            with queue_locks[directions[i]]:
                try:
                    message, message_type = queues[directions[i]].receive(block=False)
                    other_vehicle = pickle.loads(message)
                    if (other_vehicle.destination == vehicle.source and (vehicle.destination != other_vehicle.source)):
                        # Le véhicule actuel doit attendre car un autre véhicule a la priorité à droite
                        return False
                except sysv_ipc.BusyError:                   
                    # Pas de véhicule dans cette queue, continuer
                    continue
    return True


def move_vehicle(vehicle, queues):
    """
    Déplace un véhicule à travers l'intersection et le retire de la file d'attente.
    """
    with queue_locks[vehicle.source]:
        try:
            print(f"Vehicle {vehicle.vehicle_id} has passed the intersection from {vehicle.source} to {vehicle.destination}.")
        except Exception as e:
            print(f"Error moving vehicle {vehicle.vehicle_id}: {e}")


def display():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('localhost', 5000))
    server_socket.listen(1)
    print("Display process started. Waiting for connections...")

    while True:
        try:
            client_socket, addr = server_socket.accept()
            print(f"Connected to {addr}")

            while True:
                data = client_socket.recv(1024).decode('utf-8')
                if not data:
                    break
    
                try:
                    message = json.loads(data)
                    if "lights" in message:
                        print(f"État des feux : {message['lights']}")
                    if "waiting" in message:
                        print(f"Véhicules en attente : {message['waiting']}")
                    if "passing" in message:
                        print(f"Véhicules en train de passer : {message['passing']}")
                except json.JSONDecodeError:
                    print("Erreur de décodage JSON")

            client_socket.close()
        except Exception as e:
             print(f"Erreur dans le processus display : {e}")


def stopping_signal_handler(sig, frame):
    global running
    print("Signal reçu, arrêt du programme...")
    running = False


#variable globale pour contrôler l'exécution
running = True
if __name__ == "__main__":
    # On enregistre le signal handler pour l'arrêt pour SIGINT (Ctrl+C)
    signal.signal(signal.SIGINT, stopping_signal_handler)

    
    # On place l'état des feux dans un array en shared-memory
    # on considèrera que cet état peut être représenté par un int, 1 correspondant à vert et 0 à rouge
    # dans l'ordre, lights_state contient [North_state, South_state, East_state, West_state]
    lights_state = Array('i', [1, 1, 0, 0])  #par défaut, feu vert au nord et sud

    # Variable partagée pour indiquer l'origine (source) du véhicule prioritaire  : 0 = Nord, 1 = Sud, 2 = Est, 3 = Ouest, 4 = aucun prioritaire
    priority_state = Value('i', 4)
    
    directions = ["North", "South", "West", "East"]
    #Pour les message queues, on mets des clés pour y accéder
    sections = {
        "North": 1111,
        "South": 2222,
        "West": 3333,
        "East": 4444
    }
    normal = 1  # message type for normal vehicless
    priority = 2  # message type for priority vehicles

    # Create queues for each road section
    queues = create_queues()
    
    #On crée les locks qui seront nécessaire pour un accès sans conflit aux différentes queues et feux
    queue_locks = {direction: Lock() for direction in directions}
    lights_lock = Lock()

    # Create separate processes for normal traffic, priority traffic, and coordinator
    normal_process = Process(target=normal_traffic_gen, args=(queues,))
    priority_process = Process(target=priority_traffic_gen, args=(queues,))
    lights_process = Process(target=lights)
    coordinator_process = Process(target=coordinator)
    display_process = Process(target=display)

    # Start processes
    normal_process.start()
    priority_process.start()
    lights_process.start()
    coordinator_process.start()
    display_process.start()

    # Gestion de l'arrêt du programme
    signal.signal(signal.SIGINT, stopping_signal_handler)
    
    try:
        while running:
            time.sleep(0.1)  # Petite pause pour éviter une boucle infinie trop rapide
    except KeyboardInterrupt:
        print("Interruption clavier détectée, arrêt du programme...")
    finally:
        running = False
        # Arrêt des processus
        normal_process.terminate()
        priority_process.terminate()
        lights_process.terminate()
        coordinator_process.terminate()
        display_process.terminate()
        
        #on attend que les processus se terminent
        normal_process.join()
        priority_process.join()
        lights_process.join()
        coordinator_process.join()
        display_process.join()
        
        # On retire les message queues (libération des ressources à la fin)
        for queue in queues.values():
            queue.remove()
            
        print("Simulation stopped.")


