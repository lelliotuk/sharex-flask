
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
