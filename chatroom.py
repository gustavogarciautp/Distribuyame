import os
from cliente_socketio import Cliente
import json
import pickle


# Loading the client with the current ip server

if os.path.exists('ip.binary'):
	with open('ip.binary', 'rb') as ip:
		unpickler = pickle.Unpickler(ip)
		client = Cliente(unpickler.load()) # Creates the client


if __name__ == '__main__':

	ip_server = input("Digite la dirección ip del servidor: ")
	with open('ip.binary', 'wb') as ip:
		pickle.dump(ip_server, ip)

	# Opens the application
	from signup import *