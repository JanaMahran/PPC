# -*- coding: utf-8 -*-
"""
Created on Wed Jan 29 08:58:37 2025

@author: msoff
"""
from multiprocessing import Process, Value, Array
import signal
import time
import random
import os
from functools import partial


# On place l'état des feux dans un array en shared-memory
# on considèrera que cet état peut être représenté par un int, 1 correspondant à vert et 0 à rouge
# dans l'ordre, lights_state contient [North_state, South_state, East_state, West_state]
lights_state = Array('i', [1, 1, 0, 0])  #par défaut, feu vert au nord et sud

# Variable partagée pour indiquer l'origine (source) du véhicule prioritaire  : 0 = Nord, 1 = Sud, 2 = Est, 3 = Ouest, 4 = aucun prioritaire
priority_state = Value('i', 4)

def creer_vehicule_prioritaire(vehicule_prioritaire, pid_feux):
    """ Simule l'arrivée d'un véhicule prioritaire """
    attente = random.randint(10,20) #un véhicule prioritaire apparait 10 à 20 secondes après le précédent
    #print(f"Nouveau véhicule prioritaire dans {attente} secondes")
    time.sleep(attente)  # Attente avant apparition d'un véhicule prioritaire
    direction = random.randint(0,4)
    vehicule_prioritaire.value = direction
    os.kill(pid_feux, signal.SIGUSR1)  # Envoyer le signal pour que lights soit au courant
 
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
        
        else:  # Mode priorité activé
           print("Mode priorité activé, feux adaptés à la situation")
           time.sleep(3)  # Petite attente avant de revenir en mode normal
           priority_state.value = 4  # Retour au mode normal après passage du véhicule
   

if __name__ == "__main__":
    p_lights = Process(target=lights)
    p_lights.start()

    p_vehicules = Process(target=creer_vehicule_prioritaire, args=(priority_state, p_lights.pid))
    p_vehicules.start()

    p_lights.join()
    p_vehicules.join()

