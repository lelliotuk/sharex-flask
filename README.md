
# sharex-flask
Another (Flask) ShareX file upload and URL shortener

Advanced, easy-to-use, and portable

Was tired of my old Python CGI script with ~300ms requests and decided to move it to WSGI/Flask, cutting it down to ~10ms, I might upload the old script at some point

### Features
 - Simple setup
 - Short URLs, 4-character IDs, full filenames (Content-Disposition)
 - Optional file extension on URLs (simply remove or extend(?), only the first 4 characters are considered)
 - Fresh link with no duplicate files
 - Image hashing and click count stored in database (no functionality outside db yet)

### To-do
- Clean up code/PEP8
- Configurable link lengths
- Full filename in URL option
- Configurable Content-Disposition for certain filetypes (attachment/inline)
- Link/file expiry and self-destructing
- Image hashing to avoid duplicates if the file hash is inadequate(?)
- Web interface(?)
- Users(?)
- IDK

## Usage
### Setup
You only really need to change the secret key variable in `server.py`, but there are some other configurable options

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
