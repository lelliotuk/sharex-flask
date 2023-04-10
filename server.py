#!/usr/bin/python3

import os
import flask
import random
import string
import sqlite3
import time
import hashlib
import shutil
import gc
from io import BytesIO
from urllib.parse import quote as url_encode
from flask import Flask, request, redirect, send_file, make_response, Request, Response, stream_with_context

# ------------------------------- Config --------------------------------

SECRET_KEY = "!!! KEY HERE !!!"  # Can be left empty (not recommended)

# Config below is optional

# Enable image hashing, disabled by default until it is used for something
ENABLE_IMAGE_HASH = False

# Max file size for image hashing
# Prevents huge files with specific extensions consuming lots of memory
MAX_FILE_MEMORY = 30 * 1024 * 1024 # 30MB

# Absolute working directory (default is the path of this script)
BASE_DIR = os.path.dirname(os.path.realpath(__file__)) + "/"

# Database path
DB_PATH = BASE_DIR + "/uploads.sqlite"

# Upload directory
# !! Must have trailing slash
UPLOAD_DIR = BASE_DIR + "/upload/"

# Temp directory
# Uploads are written here until the checksum is calculated and the file is moved
# !! Must have trailing slash
TEMP_DIR = BASE_DIR + "/temp/"

# The first part of the URL returned
# e.g. https://example.org/
# Leave blank to use request.url_root
# !! Must have trailing slash
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


if not os.path.isdir(UPLOAD_DIR):
    os.mkdir(UPLOAD_DIR)

if not os.path.isdir(TEMP_DIR):
    os.mkdir(TEMP_DIR)

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

class Upload():
    def __init__(self, filename, total_content_length):
        self.chk = hashlib.md5()
        self.tempname = TEMP_DIR + str(time.time_ns())
        self.tempfile = open(self.tempname, "wb+")
        self.file_mem = BytesIO()
        
        self.read = self.tempfile.read
        self.readline = self.tempfile.readline
        
        self.imhash = ENABLE_IMAGE_HASH \
                  and get_ext(filename) in IMAGE_TYPES \
                  and total_content_length < MAX_FILE_MEMORY
                  
        self.buffer_funcs = [self.chk.update, self.tempfile.write]
             
        if self.imhash:
            self.buffer_funcs.append(self.file_mem.write)
        
    def write(self, data):
        for f in self.buffer_funcs:
            f(data)
    
    def seek(self, p):
        self.tempfile.seek(p)
        self.file_mem.seek(p)
    
    def move(self, dest):
        self.tempfile.close()
        shutil.move(self.tempfile.name, dest)
    
    def delete(self):
        self.tempfile.close()
        self.file_mem.close()
        if os.path.isfile(self.tempfile.name):
            os.remove(self.tempfile.name)
    
    def close(self):
        self.delete()
    
    def __del__(self):
        self.delete()


class UploadStream(Request):
    def _get_file_stream(self, total_content_length, content_type, filename=None, content_length=None):    
        return Upload(filename, total_content_length)

app.request_class = UploadStream


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
    

def timestamp():
    return int(time.time())


@app.route(CREATE_PATH, methods=['POST'])
def create():
    def stream():
        try:
            if SECRET_KEY and request.form['k'] != SECRET_KEY:
                yield "Not authenticated", 401
            
            file = request.files.get('f')
            url = request.form.get('u')
            
            if file:
                yield create_upload(file)
            
            elif url:
                yield create_redirect(url)
            
            else:
                yield "No file or URL provided", 400
        except:
            pass

    return Response(stream_with_context(stream()))

@app.route(UPLOAD_PATH + '<path:f>', methods=['GET'])
def get_file(f):
    now = timestamp()
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
        
        if file_expires > 0 and now > file_expires:
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


def rnd_id(table):
    while True:
        rnd = rnd_str(LINK_LEN)
        cur.execute(f"SELECT * FROM {table} WHERE id = ?", [rnd])
        if not cur.fetchone():
            return rnd


def create_upload(file):
    now = timestamp()

    file_chk = file.stream.chk.hexdigest()
    file_name = file.filename
    file_ext = get_ext(file_name)
    file_imghash = ''
    file_dest = UPLOAD_DIR + file_chk + '.' + file_ext
    
    if os.path.isfile(file_dest):
        file.stream.delete()
    else:
        file.stream.move(file_dest)

    if file.stream.imhash:
        try:
            file_imghash = str(imagehash.phash(Image.open(file.stream.file_mem)))
        except:
            pass
    
    cur.execute("SELECT * FROM files WHERE md5 = ?;", [file_chk])
    result = cur.fetchone()
    
    if result is None:
        cur.execute("INSERT INTO files VALUES (?,?,?,?,?,?);", 
                    [file_chk, file_imghash, now, file_name, 0, ""])
    
    link_id = rnd_id("links")
    
    cur.execute("INSERT INTO links VALUES (?,?,?,?,?,?);", 
                [link_id, file_chk, file_name, now, -1, 0])
        
    con.commit()

    return server_addr() + UPLOAD_PATH + link_id + '.' + file_ext


def create_redirect(url):
    now = timestamp()

    redir_id = rnd_id("redirects")
            
    url = http_sanitise(url)
    
    cur.execute("INSERT INTO redirects values (?,?,?,?);",
                [redir_id, url, now, 0])
        
    con.commit()
    return server_addr() + REDIRECT_PATH + redir_id




if __name__ == '__main__':
    app.run(threaded=True)
