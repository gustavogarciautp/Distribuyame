import json
import pymongo
import hashlib
import pprint
from pymongo import MongoClient

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room, rooms, Namespace, close_room, disconnect,send
client = MongoClient()

db = client.chatdistribuidos  #obtiene la base de datos

usuarios = db.usuario
salas=db.sala
users={}
sids={}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
sio = SocketIO(app)

class Servidor(Namespace):
  """docstring for Servidor"""
  def __init__(self):
    Namespace.__init__(self,'/')
    sala=salas.find_one({"Nombre":"Default"})
    if not sala:
      salas.insert_one({"Nombre":"Default","Usuarios":0})
    print("server")
    
  def on_connect(self):
    print('connect ', request.sid)

  def on_Registrarse(self,data):
    data= json.loads(data)
    campo_login=usuarios.find_one({"Login":data["Login"]})
    if campo_login:
      return json.dumps("El nombre de usuario ya existe")
    else:
      data["Password"]=hashlib.sha1(data["Password"].encode()).hexdigest()
      data["Mensajes_nuevos"]={}
      data["Mensajes_viejos"]={}
      data["Sala_creada"]=""
      data["Sala"]=""    
      usuarios.insert_one(data)
      return json.dumps("")

  def on_startsession(self,data):
    print(data)
    data= json.loads(data)
      #Verificar que no hayan usuarios con el mismo Username
    campo=usuarios.find_one({"Login":data["Login"],"Password":hashlib.sha1(data["Password"].encode()).hexdigest()})
    if campo: 
      if data["Login"] in users:
        return json.dumps("El usuario ya esta conectado")
      else:   
        sids[request.sid] = data["Login"]
        users[data["Login"]]= request.sid

        join_room('Default')
        room=self.findRoom(request.sid)
        usuarios.update_one(campo, {"$set": {"Sala":room}})

        sala= salas.find_one_and_update({"Nombre": "Default"}, {'$inc': {'Usuarios': 1}})      
        return json.dumps("")
    else:
      return json.dumps("El nombre de usuario y contraseña no coinciden", ensure_ascii=False)

  def on_mensajesprivados(self):
    mensajes={}
    user=sids[request.sid]
    campo=usuarios.find_one({"Login":user})
    mensajes["Nuevos"]=campo["Mensajes_nuevos"]
    mensajes["Viejos"]=campo["Mensajes_viejos"]
    return json.dumps(mensajes)

  def on_disconnect(self):
    print('disconect', request.sid)
    user=sids.get(request.sid,False)
    if user: 
      #print("disconect")
      self.desconectar(user)

  #Data es un string
  def on_mensaje(self,data):
    print(data)
    data2={}
    data=json.loads(data)
    user= sids[request.sid]
    room= self.findRoom(request.sid)
    data2[user]= data#data.update({"Emisor":user})
    #salas.update_one({"Nombre":room},{'$push':{"Mensajes": data2}})
    emit('recv_message',json.dumps(data2),room=room,include_self=False)

  def on_crearsala(self,nombreSala):
    nameRoom=json.loads(nombreSala)
    chatroom=salas.find_one({"Nombre":nameRoom})
    if chatroom==None:
      username=sids[request.sid]
      salas.insert_one({"Nombre":nameRoom,"Usuarios":0})
      self.on_entrarsala(nombreSala,username)
      usuarios.update_one({"Login":username},{'$set':{"Sala_creada":nameRoom}})
      return json.dumps("")
    else:
      return json.dumps("La sala "+nameRoom+" ya existe")

  def findRoom(self,sid):
    chatrooms= rooms(sid=sid)
    if (chatrooms[0]==sid):
      return chatrooms[1]
    else:
      return chatrooms[0] 

  def on_entrarsala(self,nombreSala, username=''):
    nombreSala= json.loads(nombreSala)
    sala= salas.find_one({"Nombre":nombreSala})
    if sala:
      if not username:
        username=sids[request.sid]

      chatroom= self.findRoom(request.sid)
      salas.update_one({"Nombre": chatroom}, {'$inc': {'Usuarios': -1}})
      user=usuarios.find_one({"Login":username})
      usuarios.update_one({"Login":username},{'$set':{"Sala":nombreSala}})
      self.on_eliminarsala(chatroom,user)
      leave_room(room=chatroom)
      sala=salas.find_one_and_update({"Nombre":nombreSala}, {'$inc': {'Usuarios':1}})
      join_room(room=nombreSala)
      #if len(sala["Mensajes"])>0:
      #  return json.dumps(sala["Mensajes"])
      return json.dumps("")
    else:
      return json.dumps("Error al entrar. La sala "+nombreSala+" ha sido eliminada")

  def on_salir(self, user='', room=''):
    if not user and not room:
      sid=request.sid
      user= sids[sid]
      room= self.findRoom(sid)
      answer=json.loads(self.on_eliminarsala())
      if not answer:
        return
    else:
      sid=users[user]
    if room!="Default":
      salas.update_one({"Nombre":room},{'$inc':{'Usuarios':-1}})
      leave_room(room=room, sid=sid)
      salas.update_one({"Nombre":"Default"},{'$inc':{'Usuarios':1}})
      usuarios.update_one({"Login":user},{'$set':{'Sala':'Default'}})
      join_room(room="Default", sid=sid)

  def desconectar(self, user):
    room= self.findRoom(request.sid)
    salas.update_one({"Nombre": room}, {'$inc': {'Usuarios': -1}})
    leave_room(room=room)

    usuario=usuarios.find_one({"Login":user})
    usuarios.update_one({"Login":user}, {'$set':{'Sala_creada':"",'Sala':""}})

    self.deleteroom(usuario["Sala_creada"],user)
    
    del users[user]
    del sids[request.sid]

  def on_show_users(self):
    return json.dumps(list(sids.values()))

  def on_private(self,data):
    print(data)
    data= json.loads(data)
    recp=data["Receptor"]
    exist=usuarios.find_one({"Login":recp})
    if (exist):
      idrecp=users.get(recp,False)
      user=sids[request.sid]
      data["Emisor"]=user
      del data["Receptor"]
      if idrecp:
        sio.emit('recv_private',json.dumps(data), room=idrecp)

      a=usuarios.find_one({"Login":recp,"Mensajes_nuevos."+user: {'$exists':True}})

      if a:
        usuarios.update_one({"Login":recp}, {'$push':{"Mensajes_nuevos."+user:data["Mensaje"]}})
      else:
        usuarios.update_one({"Login":recp}, {'$set':{"Mensajes_nuevos."+user:[data["Mensaje"]]}})
      return json.dumps("")
    return json.dumps("El usuario "+recp+" no existe")

  def on_read_message(self, data):
    data=json.loads(data)
    username= sids[request.sid]
    usuario=usuarios.find_one({"Login":username})
    message= usuario["Mensajes_nuevos"][data]
    if data in usuario["Mensajes_viejos"]:
      usuarios.update_one({"Login":username},{'$push':{"Mensajes_viejos."+data:{'$each':message}}})
    else:
      usuarios.update_one({"Login":username},{'$set':{"Mensajes_viejos."+data:message}})
    usuarios.update_one({"Login":username},{'$unset':{"Mensajes_nuevos."+data:""}})

  def on_listarsalas(self):
    chatrooms={}
    for sala in salas.find():
      chatrooms[sala["Nombre"]]=sala["Usuarios"]
    return json.dumps(chatrooms)

  def on_eliminarsala(self, current_room='', usuario=''):
    if not current_room and not usuario:
      username= sids[request.sid]
      current_room=self.findRoom(request.sid)
      usuario=usuarios.find_one({"Login":username})
    else:
      username= usuario["Login"]
    if usuario["Sala_creada"]==current_room:
      ret= self.deleteroom(current_room, usuario["Login"])
      usuarios.update_one({"Login":username},{'$set':{'Sala_creada':""}})
      return ret
    else:
      return json.dumps("No tiene credenciales para eliminar esta sala")

  def deleteroom(self, current_room, Login):
    print(current_room)
    if current_room:
      clientes=usuarios.find({"Sala":current_room})
      if clientes:
        for cliente in clientes:
          self.on_salir(cliente["Login"], current_room)
          if Login!=cliente["Login"]:
            emit('salir',json.dumps('La sala en la que se encontraba ha sido eliminada'), room=users[cliente["Login"]])
        close_room(room=current_room)
      salas.delete_one({"Nombre":current_room})
      return json.dumps("")

sio.on_namespace(Servidor())
if __name__ == '__main__':
  print("server1")
  sio.run(app, host='10.253.2.250',port=8000)  


