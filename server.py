#!/usr/bin/python3

import os
import flask
import random
import string
import sqlite3
import time
import hashlib
from urllib.parse import quote as urlEncode
from flask import Flask, request, redirect, send_file, make_response

#################### Config ################################

SECRET_KEY = "!!! KEY HERE !!!" # Can be left empty (not recommended)

# Config below is optional

ENABLE_IMAGE_HASH = False # Enable image hashing, disabled by default until it is used for something

BASE_DIR = os.path.dirname(os.path.realpath(__file__)) + "/" # absolute working directory (default is the path of this script)

URL_ROOT =	""		# The first part of the URL returned e.g. https://example.org/
				# !! Must have trailing slash
				# Leave blank to use request.url_root
CREATE_PATH =	"/create"	# Path for files to be uploaded or links to be shortened e.g. https://example.org/create
UPLOAD_PATH =	"/f/"		# Path for files to be accessed e.g. https://example.org/f/1234.jpg
REDIRECT_PATH =	"/r/"		# Path for redirects to be accessed e.g. https://example.org/r/abcd

############################################################

if ENABLE_IMAGE_HASH:
	from PIL import Image
	import imagehash

IMAGETYPES = ( # Types to be processed by imagehash (should be supported by imagehash/PIL)
	'jpg',
	'jpeg',
	'png',
	'gif',
	'bmp',
	'webp'
	)


epoch = int(time.time())

if not os.path.isdir(BASE_DIR + "./upload"): os.mkdir(BASE_DIR + "./upload")

dbCon = sqlite3.connect(BASE_DIR + "./uploads.sqlite")
dbCur = dbCon.cursor()

# Create file table
dbCur.execute('CREATE TABLE IF NOT EXISTS files (md5 TEXT PRIMARY KEY, imagehash TEXT, time INT, filename TEXT, downloads INT, comments TEXT);')
dbCur.execute('CREATE TABLE IF NOT EXISTS links (id TEXT PRIMARY KEY, md5 TEXT, filename TEXT, time INT, expires INT, onetime INT, FOREIGN KEY(md5) REFERENCES files(md5))')
dbCur.execute('CREATE INDEX IF NOT EXISTS idxfilehash ON files (md5)')
dbCur.execute('CREATE INDEX IF NOT EXISTS idximagehash ON files(imagehash)')
dbCur.execute('CREATE INDEX IF NOT EXISTS idxlinkid ON links (id)')

# Create redirect table
dbCur.execute('CREATE TABLE IF NOT EXISTS redirects (id text, url text, time integer, views integer, PRIMARY KEY("id"));')
dbCur.execute('CREATE INDEX IF NOT EXISTS idxredirects ON redirects (id);')

dbCon.commit()

app = Flask(__name__, static_url_path='/static', static_folder='static')

def getExt(f): return f.split(".")[-1] if '.' in f else ''
def rndStr(l=10): return ''.join(random.choice(string.ascii_letters + string.digits) for i in range(l))
def serverAddr(): return URL_ROOT or request.url_root[:-1] or ''


@app.route(CREATE_PATH, methods=['POST'])
def create():
	if SECRET_KEY and request.form['k'] != SECRET_KEY: return "Not authenticated", 401
	file = request.files.get('f')
	url = request.form.get('u')
	if file: return createUpload(file)
	if url: return createRedirect(url)
	return "No file or URL provided", 400
	


@app.route(UPLOAD_PATH + '<path:f>', methods = ['GET'])
def getFile(f):
	f = f[:4]
	dbCur.execute("SELECT links.md5,links.filename,expires,onetime,files.filename,files.time FROM links JOIN files ON links.md5=files.md5 WHERE id = ?;", [f])
	result = dbCur.fetchone()
	if result:
		fileChk, fileName, fileExpires, fileOnetime, fileOriginalName, fileTimestamp = result
		if fileExpires > 0 and epoch > fileExpires:
			dbCur.execute("DELETE FROM links WHERE id = ?;", [f])
			dbCon.commit()
			return "File does not exist or expired", 404

		if fileOnetime:
			dbCur.execute("DELETE FROM links WHERE id = ?;", [f])
		else:
			dbCur.execute("UPDATE files SET downloads = downloads + 1 WHERE md5 = ?;", [fileChk])
		dbCon.commit()
		
		filePath = BASE_DIR + "./upload/" + fileChk + "." + getExt(fileOriginalName)
		if not os.path.isfile(filePath): return "File record found but file does not exist", 500
		#return send_file(filePath, attachment_filename=fileName, conditional=True)#, as_attachment=False)
		# Hacky headers because the above does not appear to work
		response = make_response(send_file(filePath, conditional=True))
		response.headers['Content-Disposition'] = 'inline; filename="' + urlEncode(fileName) + '"'
		return response 
	else:
		return "File does not exist or expired", 404


@app.route(REDIRECT_PATH + '<path:r>', methods = ['GET'])
def getRedirect(r):
	r = r[:4]
	dbCur.execute("SELECT url FROM redirects WHERE id = ?;", [r])
	result = dbCur.fetchone()
	if result:
		dbCur.execute("UPDATE redirects SET views = views + 1 WHERE id = ?;", [r])
		dbCon.commit()
		url, = result
		return redirect(url, code=307)
	else:
		return "Link not found", 404

def createUpload(file):
	fileChk = hashlib.md5(file.read()).hexdigest()
	fileName = file.filename
	fileExt = getExt(fileName)
	fileImgHash = ''
	fileDest = BASE_DIR + './upload/' + fileChk + '.' + fileExt
	
	if ENABLE_IMAGE_HASH and fileExt in IMAGETYPES:
		try:
			file.seek(0)
			fileImgHash = str(imagehash.phash(Image.open(upload.file)))
		except:
			pass # not critical
	
	
	dbCur.execute("SELECT * FROM files WHERE md5 = ?;", [fileChk])
	result = dbCur.fetchone()
	
	if not os.path.isfile(fileDest):
		file.seek(0)
		file.save(fileDest)
	
	if result is None:
		dbCur.execute("INSERT INTO files VALUES (?,?,?,?,?,?);", [fileChk, fileImgHash, epoch, fileName, 0, ""])
	
	while True:
		rnd = rndStr(4)
		dbCur.execute("SELECT * FROM links WHERE id = ?", [rnd])
		if not dbCur.fetchone(): break
	
	
	dbCur.execute("INSERT INTO links VALUES (?,?,?,?,?,?);", [rnd, fileChk, fileName, epoch, -1, 0])
	dbCon.commit()

	return serverAddr() + UPLOAD_PATH + rnd + '.' + fileExt
	
def createRedirect(url):
	while True:
		rnd = rndStr(4)
		dbCur.execute("SELECT id FROM redirects WHERE id = ?", [rnd])
		if not dbCur.fetchone(): break
	dbCur.execute("INSERT INTO redirects values (?,?,?,?);", [rnd, url, epoch, 0])
	dbCon.commit()
	return serverAddr() + REDIRECT_PATH + rnd

if __name__ == '__main__':
    app.run(threaded=True)
