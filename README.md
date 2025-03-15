
# sharex-flask
Another (Flask) ShareX file upload and URL shortener

## Features
 - Simple setup & portable
 - Configurable URL length & characters
 - Full filenames (Content-Disposition)
 - Fresh link with no duplicate files
 - Image hashing and click count stored in database (no functionality outside db yet)

## Usage
### Setup
While you can launch the app directly through Flask, for security and performance, you should use a proper WSGI server such as uWSGI or Gunicorn, and proxy it through your web server, e.g. with WSGI ProxyPass. Alternatively, you can run the app directly in Apache2 with mod_wsgi.

Here is a sample WSGI file where the app is imported and configured without modifying it
```
#!/usr/bin/python3

import sharexsrv

application = sharexsrv.app

sharexsrv.URL_ROOT = "https://example.org"
sharexsrv.SECRET_KEY = "key here"
sharexsrv.BASE_DIR = "/var/www/sharexsrv/sharexsrv/"
```
These are the main things I recommend configuring. More options and explanations can be found in `server.py`

`SECRET_KEY` is the key used to access the API

I recommend using an absolute path for `BASE_DIR` to avoid any trouble. The database and uploads are stored here

### File uploading
POST to /create  
Form:  
`k` - Your secret key  
`f` - The file to upload  

Response:  
Plaintext generated full URL (e.g. https://example.org/f/1234.jpg)
### Creating redirects
POST to /create  
Form:  
`k` - Your secret key  
`u` - The URL to redirect to  

Response:  
Plaintext generated full URL (e.g. https://example.org/r/abcd)
