#!/usr/bin/python3

import os
import flask
import random
import string
import sqlite3
import time
import hashlib
from PIL import Image
import imagehash
from flask import Flask, request, redirect, send_file, make_response
import sys


#################### Config ################################

SECRET_KEY = "!!! KEY HERE !!!" # Can be left empty (not recommended)

# Config below is optional

ENABLE_IMAGE_HASH = False # Enable image hashing, disabled by default until it is used for something

BASE_DIR = os.path.dirname(os.path.realpath(__file__)) # absolute working directory (default is the path of this script)

URL_ROOT =                          ""			# The first part of the URL returned e.g. https://example.org/
												# !! Must have trailing slash
												# Leave blank to use request.url_root
BASE_PATH =                         ""			# Optional prefix for the path e.g. https://example.org/prefix/upload
CREATE_UPLOAD_PATH = BASE_PATH +    "/upload"	# Path for files to be uploaded e.g. https://example.org/upload
CREATE_REDIRECT_PATH = BASE_PATH +  "/redirect"	# Path for redirects to be created e.g. https://example.org/redirect
UPLOAD_PATH = BASE_PATH +           "/f/"		# Path for files to be accessed e.g. https://example.org/f/1234.jpg
REDIRECT_PATH = BASE_PATH +         "/r/"		# Path for redirects to be accessed e.g. https://example.org/r/abcd

############################################################

IMAGETYPES = ( # Types to be processed by imagehash (should be supported by imagehash/PIL)
	'jpg',
	'jpeg',
	'png',
	'gif',
	'bmp',
	'webp'
	)


epoch = int(time.time())

os.chdir(BASE_DIR)

if not os.path.isdir("./upload"): os.mkdir("./upload")

fileDbCon = sqlite3.connect("./uploads.sqlite")
fileDbCur = fileDbCon.cursor()

fileDbCur.execute('CREATE TABLE IF NOT EXISTS files (md5 TEXT PRIMARY KEY, imagehash TEXT, time INT, filename TEXT, downloads INT, comments TEXT);')
fileDbCur.execute('CREATE TABLE IF NOT EXISTS links (id TEXT PRIMARY KEY, md5 TEXT, filename TEXT, time INT, expires INT, onetime INT, FOREIGN KEY(md5) REFERENCES files(md5))')
fileDbCur.execute('CREATE INDEX IF NOT EXISTS idxfilehash ON files (md5)')
fileDbCur.execute('CREATE INDEX IF NOT EXISTS idximagehash ON files(imagehash)')
fileDbCur.execute('CREATE INDEX IF NOT EXISTS idxlinkid ON links (id)')


redirDbCon = sqlite3.connect("./redirects.sqlite")
redirDbCur = redirDbCon.cursor()
redirDbCur.execute('CREATE TABLE IF NOT EXISTS redirects (id text, url text, time integer, views integer, PRIMARY KEY("id"));')
redirDbCur.execute('CREATE INDEX IF NOT EXISTS idxredirects ON redirects (id);')

app = Flask(__name__, static_url_path='/static', static_folder='static')



def getExt(f): return f.split(".")[-1] if '.' in f else ''
def rndStr(l=10): return ''.join(random.choice(string.ascii_letters + string.digits) for i in range(l))
def serverAddr(): return URL_ROOT or request.url_root[:-1] or ''

@app.route(CREATE_UPLOAD_PATH, methods=['POST'])
def createUpload():
	if SECRET_KEY and request.form['k'] != SECRET_KEY: return "Not authenticated", 401
		
	file = request.files.get('f')
	if not file: return "No file uploaded", 400
	
	fileChk = hashlib.md5(file.read()).hexdigest()
	fileName = file.filename
	fileExt = getExt(fileName)
	fileImgHash = ''
	
	if ENABLE_IMAGE_HASH and fileExt in IMAGETYPES:
		try:
			file.seek(0)
			fileImgHash = str(imagehash.phash(Image.open(upload.file)))
		except:
			pass # not critical
	
	
	fileDbCur.execute("SELECT * FROM files WHERE md5 = ?;", [fileChk])
	result = fileDbCur.fetchone()
	if result is None:
		file.seek(0)
		file.save('./upload/' + fileChk + '.' + fileExt)
		fileDbCur.execute("INSERT INTO files VALUES (?,?,?,?,?,?);", [fileChk, fileImgHash, epoch, fileName, 0, ""])
	
	while True:
		rnd = rndStr(4)
		fileDbCur.execute("SELECT * FROM links WHERE id = ?", [rnd])
		if not fileDbCur.fetchone(): break
	
	
	fileDbCur.execute("INSERT INTO links VALUES (?,?,?,?,?,?);", [rnd, fileChk, fileName, epoch, -1, 0])
	fileDbCon.commit()

	return serverAddr() + UPLOAD_PATH + rnd + '.' + fileExt





@app.route(CREATE_REDIRECT_PATH, methods = ['POST'])
def createRedirect():
	if SECRET_KEY and request.form['k'] != SECRET_KEY: return "Unauthorised", 401
	url = request.form.get('u')
	if not url: return "No URL provided", 400
	while True:
		rnd = rndStr(4)
		redirDbCur.execute("SELECT id FROM redirects WHERE id = ?", [rnd])
		if not redirDbCur.fetchone(): break
	redirDbCur.execute("INSERT INTO redirects values (?,?,?,?);", [rnd, url, epoch, 0])
	redirDbCon.commit()
	return serverAddr() + REDIRECT_PATH + rnd



@app.route(UPLOAD_PATH + '<path:f>', methods = ['GET'])
def getFile(f):
	f = f[:4]
	fileDbCur.execute("SELECT links.md5,links.filename,expires,onetime,files.filename,files.time FROM links JOIN files ON links.md5=files.md5 WHERE id = ?;", [f])
	result = fileDbCur.fetchone()
	if result:
		fileChk, fileName, fileExpires, fileOnetime, fileOriginalName, fileTimestamp = result
		if fileExpires > 0 and epoch > fileExpires:
			fileDbCur.execute("DELETE FROM links WHERE id = ?;", [f])
			fileDbCon.commit()
			return "File does not exist or expired", 404

		if fileOnetime:
			fileDbCur.execute("DELETE FROM links WHERE id = ?;", [f])
		else:
			fileDbCur.execute("UPDATE files SET downloads = downloads + 1 WHERE md5 = ?;", [fileChk])
		fileDbCon.commit()
		
		if request.headers.get('If-None-Match') == fileChk:
			return Response(code=304)
		else:
			filePath = "./upload/" + fileChk + "." + getExt(fileOriginalName)

			#return send_file(filePath, attachment_filename=fileName, conditional=True)#, as_attachment=False)
			# Hacky headers because the above does not appear to work
			response = make_response(send_file(filePath, conditional=True))
			response.headers['Content-Disposition'] = "inline; filename=" + fileName
			return response 
	else:
		return "File does not exist or expired", 404


@app.route(REDIRECT_PATH + '<path:r>', methods = ['GET'])
def getRedirect(r):
	r = r[:4]
	redirDbCur.execute("SELECT url FROM redirects WHERE id = ?;", [r])
	result = redirDbCur.fetchone()
	if result:
		redirDbCur.execute("UPDATE redirects SET views = views + 1 WHERE id = ?;", [r])
		redirDbCon.commit()
		url, = result
		return redirect(url, code=307)
	else:
		return "Link not found", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', threaded=True)
