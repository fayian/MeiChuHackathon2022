from flask import Flask, request, abort, jsonify
from flask_api import status
from datetime import datetime
import pymysql
import random
import json
import math
import hashlib
import os
import base64
import cv2
import torch
import PIL
from PIL import Image
model = torch.hub.load('ultralytics/yolov5', 'custom', 'yolov5/best_yolov5l.pt')

#TODO: Hide credentials instead of hard coding it
db_settings = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "hackathon_app",
    "password": "password",
    "db": "hackathon",
    "charset": "utf8"
}

app = Flask(__name__)
#app.config["DEBUG"] = True
app.config['UPLOAD_FOLDER'] = "/images/"
ALLOWED_EXTENSIONS = set(['png', 'jpg'])

@app.route("/api/camera/add", methods = ['GET'])
def addCamera():	
    if "region" not in request.values.keys():
        return "Missing argument \"region\"", status.HTTP_400_BAD_REQUEST
    
    id = ""
    token = ""
    region_id = request.values["region"]

    #generate token     
    for i in range(16):
        temp = math.floor(random.random()*61)
        if temp <= 9:
            token += chr(temp + ord('0'))
        elif temp <= 35:
            token += chr(temp - 10 + ord('a'))
        else:
            token += chr(temp - 36 + ord('A'))

    #connect to database
    try:
        conn = pymysql.connect(**db_settings)
        with conn.cursor() as cursor:
            #check region_id
            cursor.execute("SELECT region_id FROM regions WHERE region_id=%s;", (region_id,) )
            if len(cursor.fetchall()) == 0: 
                return "Unknown region_id", status.HTTP_400_BAD_REQUEST

            #generate id
            again = True
            while again:
                again = False
                id = ""
                for i in range(10):
                    temp = math.floor(random.random()*35)
                    if temp <= 9:
                        id += chr(temp + ord('0'))
                    else:
                        id += chr(temp - 10 + ord('A'))

                cursor.execute("SELECT camera_id FROM cameras WHERE camera_id=%s;", id)
                again = bool(cursor.fetchall()) #generate again if the result isn't empty

            #upload data to database
            command = "INSERT INTO cameras(camera_id,token, region_id, name, last_update) VALUES(%s,%s,%s,%s,CURRENT_TIMESTAMP());"
            cursor.execute(command, (id, hashlib.sha256(token.encode()).hexdigest(), region_id, id))
            conn.commit()

            #response
            print("[Log] Camera(%s) added in region %s" % (id, region_id))
            return jsonify({"id":id, "token":token}) #TODO: encrypt token            

    except Exception as e:
        print(e)
        abort(500)


#TODO: purification, prevent malcious code from being uploaded
@app.route("/api/camera/upload", methods = ['POST'])
def uploadImage():
    #get request body
    data = request.form
    if "id" not in data.keys(): return "Missing argument \"id\"", status.HTTP_400_BAD_REQUEST
    if "token" not in data.keys(): return "Missing argument \"token\"", status.HTTP_400_BAD_REQUEST
    if "image" not in data.keys(): return "Missing argument \"image\"", status.HTTP_400_BAD_REQUEST
    id = data["id"]
    token = data["token"]
    image = base64.b64decode(data["image"])

    #upload image
    filePath = "images/" #TODO: convert or maybe compress the image to a smaller file type.
    filePath += str(datetime.now().strftime("%d%m%Y%H%M%S")) + ".jpg"
    f = open(filePath, "wb")
    f.write(image)
    f.close()

    #modify image and redetect for helmets
    image = Image.open(filePath)
    # image = image.resize((2274, 1080))
    image = image.rotate(270)
    image.save(filePath)
    results = model(filePath)
    results.save()
    # image = cv2.imread(str(filePath))
    # image = cv2.resize(image, (674, 320), interpolation=cv2.INTER_AREA)
    # cv2.imwrite("RESI" + filePath, image)

    #update database
    try:        
        conn = pymysql.connect(**db_settings)
        with conn.cursor() as cursor:
            #upload data to database
            cursor.execute("INSERT INTO images(camera_id, file_path) VALUES(%s, %s);", (id, filePath))
            cursor.execute("UPDATE cameras SET last_update=CURRENT_TIMESTAMP() WHERE camera_id=%s", id)
            conn.commit()
    except Exception as e:
        print(e)
        abort(500)

    return "Success"

@app.route("/api/client/cameraList", methods = ['GET'])
def getCameraList():
    #let region_id=0 means all cameras

    if "region" not in request.values: return "Missing argument \"region\"", status.HTTP_400_BAD_REQUEST
    region_id = int(request.values["region"])

    try:        
        conn = pymysql.connect(**db_settings)
        with conn.cursor() as cursor:
            if region_id == 0:
                cursor.execute("SELECT name,region_id,last_update FROM cameras ORDER BY last_update DESC;")
            else:
                cursor.execute("SELECT name,region_id,last_update FROM cameras WHERE region_id = %s ORDER BY last_update DESC;", region_id)
            
            row_headers=[x[0] for x in cursor.description]
            rows = cursor.fetchall()
            result=[]
            for row in rows:
                result.append(dict(zip(row_headers, row)))

    except Exception as e:
        print(e)
        abort(500)

    return json.dumps(result, default=str)

@app.route("/api/client/renameCamera", methods = ['POST'])
def renameCamera():
    data = request.form
    if "id" not in data.keys(): return "Missing argument \"id\"", status.HTTP_400_BAD_REQUEST
    if "name" not in data.keys(): return "Missing argument \"name\"", status.HTTP_400_BAD_REQUEST
    id = data["id"]
    name = data["name"]

    try:        
        conn = pymysql.connect(**db_settings)
        with conn.cursor() as cursor:            
            cursor.execute("SELECT camera_id,token FROM cameras WHERE camera_id=%s;", id)
            if len(cursor.fetchall()) == 0:
                return "Camera doesn't exist", status.HTTP_400_BAD_REQUEST

            cursor.execute("UPDATE cameras SET name=%s WHERE camera_id=%s", (name, id))
            conn.commit()

    except Exception as e:
        print(e)
        abort(500)

    return "Success"


@app.route("/api/client/inspect", methods = ['GET'])
def inspectCamera():
    if "id" not in request.values: return "Missing argument \"id\"", status.HTTP_400_BAD_REQUEST
    id = request.values["id"]

    try:        
        conn = pymysql.connect(**db_settings)
        with conn.cursor() as cursor:            
            cursor.execute("SELECT camera_id,file_path,image_date FROM images WHERE camera_id = %s ORDER BY image_date DESC LIMIT 10;", id)
            
            row_headers=[x[0] for x in cursor.description]
            rows = cursor.fetchall()
            result=[]
            for row in rows:
                result.append(dict(zip(row_headers, row)))

    except Exception as e:
        print(e)
        abort(500)

    return json.dumps(result, default=str)

app.run(port=3000)