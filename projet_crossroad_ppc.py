from multiprocessing import Process, Value, Array
import signal
import sysv_ipc
import random
import time
import os
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
    A CHANGER POUR GENERER VEHICULE ET PAS VEHICULE MESSAGE / POUR GENERER VEHICULE -ET- CREER LE MESSAGE (avec ? on peut envoyer un objet ?)
    Generates a vehicle message with a random source and destination,
    and sends it to the appropriate queue based on its source.
    """
    source = random.choice(directions)
    destination = random.choice([d for d in directions if d != source])  # Avoid same source & destination
    
    vehicle_data = f"{vehicle_type},{source},{destination}".encode()  # Encode as bytes
    
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
                time.sleep(5)  # Attente 5s
        
        else:
           print("Mode priorité activé, feux adaptés à la situation")
           time.sleep(3)  # Petite attente avant de revenir en mode normal
           priority_state.value = 4  # Retour au mode normal après passage du véhicule

    
def create_queues():
    #pour creer message queues pour chaque section
    queues = {}
    for direction, key in sections.items():
        try:
            queues[direction] = sysv_ipc.MessageQueue(key, sysv_ipc.IPC_CREX)  # Create new queue
        except sysv_ipc.ExistentialError:
            queues[direction] = sysv_ipc.MessageQueue(key)  # Attach to existing queue
    return queues

def access_queues():
    queues = {}
    for direction, key in directions:
        queues[direction] = sysv_ipc.MessageQueue(key)  # Attach to existing queue
    return queues


def coordinator():
    #read les queues pour les véhicules 
    queues = access_queues()
    
    while True:
        for direction, queue in queues.items():
            # TO DO: CHANGER L'ACCES AUX MESSAGE QUEUES, 0.5 sleep louche
            try:
                # Receive a message (non-blocking)
                message, message_type = queue.receive(block=False)
                vehicle_data = message.decode()
                vehicle_type, source, destination = vehicle_data.split(",")

                is_priority = (int(vehicle_type) == priority)

                print(f"Coordinator: Processing {'Priority' if is_priority else 'Normal'} vehicle from {source} to {destination}")

                # TODO: Implement traffic light handling and vehicle movement logic
                
            except sysv_ipc.BusyError:
                # No messages in this queue, continue checking others
                continue

        time.sleep(0.5)
        
 

# if __name__ == "__main__":
#     p_lights = Process(target=lights)
#     p_lights.start()

#     p_vehicules = Process(target=creer_vehicule_prioritaire, args=(priority_state, p_lights.pid))
#     p_vehicules.start()

#     p_lights.join()
#     p_vehicules.join()




if __name__ == "__main__":
    # Global flag to stop the simulation
    running = True
    
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

    # Create separate processes for normal traffic, priority traffic, and coordinator
    normal_process = Process(target=normal_traffic_gen, args=(queues,))
    priority_process = Process(target=priority_traffic_gen, args=(queues,))
    lights_process = Process(target=lights)
    coordinator_process = Process(target=coordinator)

    # Start processes
    normal_process.start()
    priority_process.start()
    lights_process.start()
    coordinator_process.start()

    # Run the program for a specific amount of time
    try:
        time.sleep(30)
    finally:
        running = False
        normal_process.join()
        priority_process.join()
        coordinator_process.join()
        
        # Remove message queues (libération des ressources à la fin)
        for queue in queues.values():
            queue.remove()
            
        print("Simulation stopped.")


