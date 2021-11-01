#!/usr/bin/python3

import os
import flask
import random
import string
import sqlite3
import time
import hashlib
from urllib.parse import quote as url_encode
from flask import Flask, request, redirect, send_file, make_response

# ------------------------------- Config --------------------------------

SECRET_KEY = "!!! KEY HERE !!!"  # Can be left empty (not recommended)

# Config below is optional


# Enable image hashing, disabled by default until it is used for something
ENABLE_IMAGE_HASH = False

# Absolute working directory (default is the path of this script)
BASE_DIR = os.path.dirname(os.path.realpath(__file__)) + "/"

# Database path
DB_PATH = BASE_DIR + "/uploads.sqlite"

# Upload directory
# !! Must have trailing slash
UPLOAD_DIR = BASE_DIR + "/upload/"

# The first part of the URL returned
# e.g. https://example.org/
# !! Must have trailing slash
# Leave blank to use request.url_root
URL_ROOT = ""

# Path for files to be uploaded or links to be shortened
# e.g. https://example.org/create
CREATE_PATH = "/create" 

# Path for files to be accessed
# e.g. https://example.org/f/1234.jpg
UPLOAD_PATH = "/f/"

# Path for redirects to be accessed
# e.g. https://example.org/r/abcd
REDIRECT_PATH = "/r/"

# Possible characters for random link generation
# Default is absolutely fine (a-Z, 0-9)
# 14 Million combinations with 4 characters
# Do not use '.' and avoid URL-sensitive characters
LINK_CHARS = string.ascii_letters + string.digits

# Generated link length
# e.g. https://example.org/f/1234.jpg is 4
LINK_LEN = 4

# -----------------------------------------------------------------------

if ENABLE_IMAGE_HASH:
    from PIL import Image
    import imagehash

# Types to be processed by imagehash (should be supported by imagehash/PIL)
IMAGE_TYPES = (
    'jpg',
    'jpeg',
    'png',
    'gif',
    'bmp',
    'webp')


epoch = int(time.time())

if not os.path.isdir(UPLOAD_DIR):
    os.mkdir(UPLOAD_DIR)

con = sqlite3.connect(DB_PATH)
cur = con.cursor()


# Create file table
cur.execute('''
    CREATE TABLE IF NOT EXISTS files (
        md5 TEXT PRIMARY KEY,
        imagehash TEXT, 
        time INT,
        filename TEXT,
        downloads INT, 
        comments TEXT
    );''')

cur.execute('''
    CREATE TABLE IF NOT EXISTS links (
        id TEXT PRIMARY KEY, 
        md5 TEXT, 
        filename TEXT, 
        time INT, 
        expires INT, 
        onetime INT, 
        FOREIGN KEY(md5) REFERENCES files(md5)
    );''')


# Create redirect table
cur.execute('''
    CREATE TABLE IF NOT EXISTS redirects (
        id text, 
        url text, 
        time integer, 
        views integer, 
        PRIMARY KEY("id")
    );''')


# Index
cur.execute('CREATE INDEX IF NOT EXISTS idxfilehash ON files (md5)')
cur.execute('CREATE INDEX IF NOT EXISTS idximagehash ON files(imagehash)')
cur.execute('CREATE INDEX IF NOT EXISTS idxlinkid ON links (id)')
cur.execute('CREATE INDEX IF NOT EXISTS idxredirects ON redirects (id);')

con.commit()


app = Flask(__name__, static_url_path='/static', static_folder='static')


def get_ext(f):
    return f.split(".")[-1] if '.' in f else ''
    
    
def rnd_str(l=10):
    return ''.join(random.choice(LINK_CHARS) for i in range(l))
    
    
def server_addr():
    return URL_ROOT or request.url_root[:-1] or ''
    
    
def http_sanitise(h):
    h = h.replace("\n", "") \
         .replace("\r", "")
    return h
    # Basic sanitise    


@app.route(CREATE_PATH, methods=['POST'])
def create():
    if SECRET_KEY and request.form['k'] != SECRET_KEY:
        return "Not authenticated", 401
        
    file = request.files.get('f')
    url = request.form.get('u')
    
    if file:
        return create_upload(file)
    
    elif url:
        return create_redirect(url)
    
    else:
        return "No file or URL provided", 400
    

@app.route(UPLOAD_PATH + '<path:f>', methods=['GET'])
def get_file(f):
    f = f.split(".",1)[0]
    
    cur.execute('''
        SELECT 
            links.md5, 
            links.filename, 
            expires, 
            onetime, 
            files.filename, 
            files.time 
        FROM 
            links 
            JOIN files ON links.md5 = files.md5 
        WHERE 
            id = ?;
        ''', [f])
    
    result = cur.fetchone()
    if result:
        (file_chk, file_name, file_expires,
            file_onetime, file_origname, file_timestamp) = result
        
        if file_expires > 0 and epoch > file_expires:
            cur.execute("DELETE FROM links WHERE id = ?;", [f])
            con.commit()
            return "File does not exist or expired", 404

        if file_onetime:
            cur.execute("DELETE FROM links WHERE id = ?;", [f])
        else:
            cur.execute('''
                UPDATE 
                    files 
                SET 
                    downloads = downloads + 1 
                WHERE 
                    md5 = ?;
                ''', [file_chk])
                    
        con.commit()
        
        file_path = UPLOAD_DIR + \
            file_chk + "." + get_ext(file_origname)
        
        if not os.path.isfile(file_path):
            return "File record found but file does not exist", 500

        file_name = url_encode(file_name)
        response = make_response(send_file(file_path, conditional=True))
        
        cont_disp = 'inline; filename="' + file_name + '"'
        response.headers['Content-Disposition'] = cont_disp
            
        # Inline content disposisition doesn't work with send_file??
        
        return response 
        
    else:
        return "File does not exist or expired", 404


@app.route(REDIRECT_PATH + '<path:r>', methods=['GET'])
def get_redirect(r):
    r = r.split(".",1)[0]
    
    cur.execute("SELECT url FROM redirects WHERE id = ?;", [r])
    result = cur.fetchone()
    
    if result:
        cur.execute('''
            UPDATE 
                redirects 
            SET 
                views = views + 1 
            WHERE 
                id = ?;
            ''', [r])
            
        con.commit()
        url, = result
        return redirect(url, code=307)
    else:
        return "Link not found", 404


def create_upload(file):
    file_chk = hashlib.md5(file.read()).hexdigest()
    file_name = file.filename
    file_ext = get_ext(file_name)
    file_imghash = ''
    file_dest = UPLOAD_DIR + file_chk + '.' + file_ext
    
    if ENABLE_IMAGE_HASH and file_ext in IMAGE_TYPES:
        try:
            file.seek(0)
            file_imghash = str(imagehash.phash(Image.open(upload.file)))
        except:
            pass  # not critical
    
    cur.execute("SELECT * FROM files WHERE md5 = ?;", [file_chk])
    result = cur.fetchone()
    
    if not os.path.isfile(file_dest):
        file.seek(0)
        file.save(file_dest)
    
    if result is None:
        cur.execute("INSERT INTO files VALUES (?,?,?,?,?,?);", 
                    [file_chk, file_imghash, epoch, file_name, 0, ""])
    
    while True:
        rnd = rnd_str(LINK_LEN)
        cur.execute("SELECT * FROM links WHERE id = ?", [rnd])
        if not cur.fetchone():
            break
    
    cur.execute("INSERT INTO links VALUES (?,?,?,?,?,?);", 
                [rnd, file_chk, file_name, epoch, -1, 0])
        
    con.commit()

    return server_addr() + UPLOAD_PATH + rnd + '.' + file_ext


def create_redirect(url):
    while True:
        rnd = rnd_str(LINK_LEN)
        cur.execute("SELECT id FROM redirects WHERE id = ?", [rnd])
        if not cur.fetchone():
            break
            
    url = http_sanitise(url)
    
    cur.execute("INSERT INTO redirects values (?,?,?,?);",
                [rnd, url, epoch, 0])
        
    con.commit()
    return server_addr() + REDIRECT_PATH + rnd


if __name__ == '__main__':
    app.run(threaded=True)
