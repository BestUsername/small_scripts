#!/usr/bin/env python3
import time     # allows sleeping to prevent duplicate faces
import sys      # allows reading argument variable
import requests # allow web request
import uuid     # for unique filenames
import shutil   # to save image to disk

# downloads and saves a face
def grab_face():
    url = "https://thispersondoesnotexist.com/image"
    
    filename = '{}.jpg'.format(str(uuid.uuid4()))
    r = requests.get(url, stream=True)
    if r.status_code == 200:
        r.raw.decode_content = True
        with open(filename,'wb') as f:
            shutil.copyfileobj(r.raw, f)
    else:
        raise Exception('Status Code {}'.format(r.status_code))
    return filename

def show_usage_and_quit(message):
    print(message)
    print('Usage:\n{} [COUNT=1]'.format(sys.argv[0]))
    exit(-1)

if __name__ == '__main__':
    # only allow one additional argument
    if len(sys.argv) > 2:
        show_usage_and_quit('Too many arguments')
    # if no count argument given, only retrieve one face
    try:
        count = int(sys.argv[1]) if len(sys.argv) == 2 else 1
    except Exception as e:
        show_usage_and_quit('Invalid argument: {}'.format(sys.argv[1]))
    
    print('Fetching {} faces:'.format(count))
    for id in range(count):
        try:
            print('{}\tSUCCESS: {}'.format(id+1, grab_face()))
            time.sleep(1)
        except Exception as e:
            print('{}\tERROR: {}'.format(id, e))
    exit(0)
