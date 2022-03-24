#!/usr/bin/env python3

import argparse # for argument parsing
import logging  # to log
import time     # allows sleeping to prevent duplicate faces
import requests # allow web GET request
import uuid     # for unique filenames
import shutil   # to save image to disk


# generates a unique filename with optional prefix and extension
def generate_unique_filename(extension, prefix):
    extension = extension or ''
    prefix = prefix or ''

    # if extension is non-empty, should start with a period
    if extension and not extension.startswith('.'):
        extension = '.' + extension

    return f'{prefix}{str(uuid.uuid4())}{extension}'

# downloads and saves a face
def grab_face_and_return_filename(prefix):
    url = "https://thispersondoesnotexist.com/image"
    
    filename = generate_unique_filename(prefix=prefix, extension='jpg')

    r = requests.get(url, stream=True)
    if r.status_code == 200:
        r.raw.decode_content = True
        with open(filename,'wb') as f:
            shutil.copyfileobj(r.raw, f)
    else:
        raise Exception('Status Code {}'.format(r.status_code))
    return filename

# main function of script - grab faces
def main(count, sleep, prefix):
    logging.info('Fetching {} faces:'.format(count))
    for id in range(count):
        try:
            filename = grab_face_and_return_filename(prefix)

            logging.debug('{}\tSUCCESS'.format(id+1))
            logging.info(f'{filename}')
        except Exception as e:
            message = '{}\tERROR: {}'.format(id, e)
            logging.error(message)
            sys.exit(message)

        if id +1 < count:
                time.sleep(sleep)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Gather unique faces from thispersondoesnotexist.com')

    parser.add_argument('-v', '--verbose', action='count', help='logging level - can stack like -v, -vv etc: DEFAULT WARNING', default=1)
    parser.add_argument('-c', '--count', type=int, help='how many images to GET: DEFAULT 1', default=1)
    parser.add_argument('-s', '--sleep', type=int, help='how many seconds to wait between GETs (prevents duplicate images): DEFAULT 1s', default=1)
    parser.add_argument('-p', '--prefix', type=str, help='optional prefix for output filenames', default='')
    
    args = parser.parse_args()

    arg_count = args.count
    arg_sleep = args.sleep
    arg_prefix = args.prefix

    # defaults to showing WARNING, ERROR and CRITICAL. Each argument will add: INFO(-v), DEBUG(-vv)
    arg_verbose = 40 - (10*args.verbose) if args.verbose > 0 else 0

    logging.basicConfig(level=arg_verbose, format='%(asctime)s %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    logging.debug(f'Parameter "count" has value {arg_count}')
    logging.debug(f'Parameter "sleep" has value {arg_sleep}')
    logging.debug(f'Parameter "prefix" has value {arg_prefix}')
    logging.debug(f'Parameter "verbose" has value {arg_verbose}')
    
    main(count=arg_count, sleep=arg_sleep, prefix=arg_prefix)
