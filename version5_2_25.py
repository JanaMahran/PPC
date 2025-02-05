#!/usr/bin/env python3
"""
PPC Project: At the crossroads (complete simulation with waiting buffer)
Authors: Razmig Kéchichian & Tristan Roussillon (modified)
This simulation involves 5 processes:
 • normal_traffic_gen: Generates normal vehicles.
 • priority_traffic_gen: Generates high‐priority vehicles.
 • coordinator: Processes vehicles from message queues based on traffic lights and traffic rules.
 • lights: Alternates lights normally and adapts to high‐priority vehicles.
 • display: Provides a socket connection to view the simulation state.
 
Traffic rules implemented:
  - Vehicles only proceed on green, except if they are turning right.
  - A right turn is defined as:
      North → East, East → South, South → West, West → North.
  - Priority vehicles are allowed to pass immediately.
  - Vehicles that cannot cross are stored in a local waiting buffer until allowed.
"""

import os
import signal
import random
import socket
from functools import partial
from multiprocessing import Process, Value, Array, Event
import sysv_ipc

# --------------------
# Global Constants
# --------------------
# IMPORTANT: The order in DIRECTIONS is critical.
# 0: North, 1: South, 2: East, 3: West, and 4: No active priority vehicle.
DIRECTIONS = ["North", "South", "East", "West"]

# Mapping to determine a right turn.
RIGHT_TURN_MAP = {
    "North": "East",
    "East": "South",
    "South": "West",
    "West": "North"
}

# Each road section is assigned a unique key for the SysV IPC message queue.
SECTIONS = {"North": 1111, "South": 2222, "East": 3333, "West": 4444}
NORMAL = 1    # message type for normal vehicles
PRIORITY = 2  # message type for priority vehicles
NO_PRIORITY = 4  # value for priority_state indicating no active priority vehicle

# --------------------
# Vehicle Class
# --------------------
class Vehicle:
    def __init__(self, vehicle_id, source, destination, priority=False):
        self.vehicle_id = vehicle_id
        self.source = source
        self.destination = destination
        self.priority = priority

    def __str__(self):
        return f"\n{'Priority' if self.priority else 'Normal'} Vehicle {self.vehicle_id} from {self.source} to {self.destination}"

# --------------------
# Message Queue Functions
# --------------------
def create_queues():
    """Creates message queues for each road section."""
    queues = {}
    for direction, key in SECTIONS.items():
        try:
            queues[direction] = sysv_ipc.MessageQueue(key, sysv_ipc.IPC_CREX)
        except sysv_ipc.ExistentialError:
            queues[direction] = sysv_ipc.MessageQueue(key)
    return queues

# --------------------
# Process Functions
# --------------------

def normal_traffic_gen(queues, stop_event):
    """
    Generates normal vehicles at random intervals and sends them to the appropriate queue.
    (The delay here simulates arrival time.)
    """
    vehicle_id = 0
    while not stop_event.is_set():
        source = random.choice(DIRECTIONS)
        destination = random.choice([d for d in DIRECTIONS if d != source])
        vehicle = Vehicle(vehicle_id, source, destination, priority=False)
        # Message format: "vehicle_type,source,destination"
        message_data = f"{NORMAL},{source},{destination}".encode()
        try:
            queues[source].send(message_data, block=False)
        except sysv_ipc.BusyError:
            pass
        print(f"[NormalGen] Generated Normal Vehicle {vehicle_id} from {source} to {destination}")
        vehicle_id += 1
        # Use stop_event.wait to simulate arrival delay
        stop_event.wait(random.uniform(2, 4))
    print("[NormalGen] Terminating.")

def priority_traffic_gen(queues, lights_pid, priority_state, stop_event):
    """
    Generates priority vehicles less frequently.
    Updates the shared priority_state and signals the lights process.
    """
    vehicle_id = 0
    while not stop_event.is_set():
        source = random.choice(DIRECTIONS)
        destination = random.choice([d for d in DIRECTIONS if d != source])
        direction_index = DIRECTIONS.index(source)
        with priority_state.get_lock():
            priority_state.value = direction_index
        vehicle = Vehicle(vehicle_id, source, destination, priority=True)
        message_data = f"{PRIORITY},{source},{destination}".encode()
        try:
            queues[source].send(message_data, block=False)
        except sysv_ipc.BusyError:
            pass
        print(f"[PriorityGen] Generated Priority Vehicle {vehicle_id} from {source} to {destination}")
        # Signal the lights process that a priority vehicle is approaching.
        os.kill(lights_pid, signal.SIGUSR1)
        vehicle_id += 1
        stop_event.wait(random.uniform(6, 8))
    print("[PriorityGen] Terminating.")

def coordinator(queues, lights_state, stop_event):
    """
    Processes vehicles from each message queue based on traffic light state and traffic rules.
    Instead of requeueing immediately into the message queue (which leads to repeated processing),
    vehicles that cannot yet cross are stored in a local waiting buffer per direction.
    On each iteration, waiting vehicles are rechecked and processed if conditions now allow.
    Traffic rules:
      - Priority vehicles always cross.
      - Normal vehicles that are turning right (as defined by RIGHT_TURN_MAP) cross regardless.
      - Other normal vehicles cross only if the light is green.
    """
    # Local waiting buffer: dictionary mapping direction to list of message bytes.
    waiting = {direction: [] for direction in DIRECTIONS}
    
    while not stop_event.is_set():
        # First, check waiting vehicles for each direction.
        for direction in DIRECTIONS:
            if waiting[direction]:
                with lights_state.get_lock():
                    current_light = lights_state[DIRECTIONS.index(direction)]
                new_waiting = []
                for message in waiting[direction]:
                    message_str = message.decode()
                    vehicle_type, source, destination = message_str.split(",")
                    vehicle_type = int(vehicle_type)
                    is_priority = (vehicle_type == PRIORITY)
                    turning_right = (destination == RIGHT_TURN_MAP[source])
                    
                    allowed_to_cross = False
                    if is_priority:
                        allowed_to_cross = True
                    elif turning_right:
                        allowed_to_cross = True
                    elif current_light == 1:
                        allowed_to_cross = True
                        
                    if allowed_to_cross:
                        print(f"[Coordinator] Processing waiting {'Priority' if is_priority else 'Normal'} Vehicle from {source} to {destination} {'(Right Turn)' if turning_right else ''}")
                        # (Vehicle is processed and removed from waiting.)
                    else:
                        new_waiting.append(message)
                waiting[direction] = new_waiting

        # Now process new messages from the queues.
        for direction, queue in queues.items():
            try:
                message, msg_type = queue.receive(block=False)
            except sysv_ipc.BusyError:
                continue

            message_str = message.decode()
            vehicle_type, source, destination = message_str.split(",")
            vehicle_type = int(vehicle_type)
            is_priority = (vehicle_type == PRIORITY)
            turning_right = (destination == RIGHT_TURN_MAP[source])
            with lights_state.get_lock():
                current_light = lights_state[DIRECTIONS.index(source)]
                
            allowed_to_cross = False
            if is_priority:
                allowed_to_cross = True
            elif turning_right:
                allowed_to_cross = True
            elif current_light == 1:
                allowed_to_cross = True

            if allowed_to_cross:
                print(f"[Coordinator] Processing {'Priority' if is_priority else 'Normal'} Vehicle from {source} to {destination} {'(Right Turn)' if turning_right else ''}")
                # (Vehicle processed – do nothing further.)
            else:
                print(f"[Coordinator] Vehicle from {source} to {destination} waiting (light red). Adding to waiting buffer.")
                waiting[source].append(message)
        stop_event.wait(0.1)
    print("[Coordinator] Terminating.")

def lights(lights_state, priority_state, stop_event):
    """
    Manages the traffic lights. In normal mode, alternates between:
      - North/South green, East/West red, and vice versa.
    When a priority signal (SIGUSR1) is received, adjusts lights so that only the direction of the
    priority vehicle (in priority_state) is green.
    """
    def priority_sig_handler(sig, frame):
        if sig == signal.SIGUSR1:
            with priority_state.get_lock():
                direction_index = priority_state.value
            print(f"[Lights] Priority vehicle detected from {DIRECTIONS[direction_index]}! Adjusting lights.")
            with lights_state.get_lock():
                for i in range(4):
                    lights_state[i] = 0
                lights_state[direction_index] = 1

    signal.signal(signal.SIGUSR1, priority_sig_handler)

    normal_cycle = True
    while not stop_event.is_set():
        with priority_state.get_lock():
            current_priority = priority_state.value
        if current_priority == NO_PRIORITY:
            if normal_cycle:
                with lights_state.get_lock():
                    # North and South green (indices 0 and 1), East and West red (indices 2 and 3)
                    lights_state[0] = lights_state[1] = 1
                    lights_state[2] = lights_state[3] = 0
                print("[Lights] North/South green, East/West red")
                if stop_event.wait(4):
                    break
                normal_cycle = not normal_cycle
            else:
                with lights_state.get_lock():
                    # East and West green (indices 2 and 3), North and South red (indices 0 and 1)
                    lights_state[0] = lights_state[1] = 0
                    lights_state[2] = lights_state[3] = 1
                print("[Lights] East/West green, North/South red")
                if stop_event.wait(5):
                    break
                normal_cycle = not normal_cycle
        else:
            print("[Lights] Priority mode active. Holding current state.")
            if stop_event.wait(3):
                break
            with priority_state.get_lock():
                priority_state.value = NO_PRIORITY
    print("[Lights] Terminating.")

def display(lights_state, stop_event, host="localhost", port=9999):
    """
    A simple TCP server that accepts a connection from a client (e.g., telnet)
    and periodically sends the current state of the traffic lights.
    Uses stop_event.wait() for periodic timing.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((host, port))
    s.listen(1)
    s.settimeout(1)  # so we can check for stop_event regularly
    print(f"[Display] Waiting for connection on {host}:{port} ...")
    conn = None
    try:
        while not stop_event.is_set():
            if conn is None:
                try:
                    conn, addr = s.accept()
                    print(f"[Display] Connected by {addr}")
                except socket.timeout:
                    continue
            with lights_state.get_lock():
                current_state = list(lights_state)
            state_str = f"Lights State: {current_state}\n"
            try:
                conn.sendall(state_str.encode())
            except (BrokenPipeError, ConnectionResetError):
                conn = None
            if stop_event.wait(1):
                break
    finally:
        s.close()
    print("[Display] Terminating.")

# --------------------
# Main function
# --------------------
if __name__ == "__main__":
    # Create shared memory objects (which include internal locks).
    lights_state = Array('i', [1, 1, 0, 0])  # Initially: North & South green.
    priority_state = Value('i', NO_PRIORITY)  # NO_PRIORITY (4) means no active priority vehicle.

    # Create an Event to signal processes to stop.
    stop_event = Event()

    # Create message queues for each road section.
    queues = create_queues()

    # Start the lights process first.
    lights_process = Process(target=lights, args=(lights_state, priority_state, stop_event))
    lights_process.start()
    # Allow the lights process time to start and register its signal handler.
    stop_event.wait(1)

    # Start the normal traffic generator.
    normal_process = Process(target=normal_traffic_gen, args=(queues, stop_event))
    normal_process.start()

    # Start the priority traffic generator (pass the lights process PID so it can be signaled).
    priority_process = Process(target=priority_traffic_gen, args=(queues, lights_process.pid, priority_state, stop_event))
    priority_process.start()

    # Start the coordinator.
    coordinator_process = Process(target=coordinator, args=(queues, lights_state, stop_event))
    coordinator_process.start()

    # Start the display process.
    display_process = Process(target=display, args=(lights_state, stop_event))
    display_process.start()

    # Run the simulation for a fixed duration.
    try:
        simulation_duration = 30  # seconds
        stop_event.wait(simulation_duration)
    except KeyboardInterrupt:
        print("[Main] Simulation interrupted by user.")
    finally:
        stop_event.set()

    # Wait for processes to terminate.
    normal_process.join()
    priority_process.join()
    coordinator_process.join()
    lights_process.join()
    display_process.join()

    # Clean up: remove all message queues.
    for q in queues.values():
        try:
            q.remove()
        except sysv_ipc.ExistentialError:
            pass

    print("[Main] Simulation terminated.")
