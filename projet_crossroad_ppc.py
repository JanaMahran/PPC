import sysv_ipc
import random
import time
import multiprocessing

class Vehicle:
    def __init__(self, vehicle_id, source, destination, priority=False):
        self.vehicle_id = vehicle_id
        self.source = source
        self.destination = destination
        self.priority = priority

    def __str__(self):
        return f"/n{'Priority' if self.priority else 'Normal'} Vehicle {self.vehicle_id} from {self.source} to {self.destination}"

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

def generate_vehicle(vehicle_type, queues):
    """
    Generates a vehicle message with a random source and destination,
    and sends it to the appropriate queue based on its source.
    """
    #genere vehicule message avec source et destination random, et l'envoie au queue based on the source
    while True:
        source = random.choice(directions)
        destination = random.choice([d for d in directions if d != source])  # Avoid same source & destination
        
        vehicle_data = f"{vehicle_type},{source},{destination}".encode()  # Encode as bytes
        
        queues[source].send(vehicle_data, type=vehicle_type)  # Send message to source queue
        print(f"Generated {('Normal' if vehicle_type == normal else 'Priority')} vehicle: {source} -> {destination}")

        # Control frequency of normal vs priority vehicles
        if vehicle_type == normal:
            time.sleep(random.uniform(2, 4))  # Normal vehicles are more frequent
        else:
            time.sleep(random.uniform(6, 8))  # Priority vehicles are less frequent

def normal_traffic_gen(queues):
    generate_vehicle(normal, queues)

def priority_traffic_gen(queues):
    generate_vehicle(priority, queues)
    
def coordinator():
    #reads les cehivules des queues 
    queues = create_queues()
    
    while True:
        for direction, queue in queues.items():
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

if __name__ == "__main__":
    # Global flag to stop the simulation
    running = True
    
    # Create queues for each road section
    queues = create_queues()

    # Create separate processes for normal traffic, priority traffic, and coordinator
    normal_process = multiprocessing.Process(target=normal_traffic_gen, args=(queues,))
    priority_process = multiprocessing.Process(target=priority_traffic_gen, args=(queues,))
    coordinator_process = multiprocessing.Process(target=coordinator)

    # Start processes
    normal_process.start()
    priority_process.start()
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


