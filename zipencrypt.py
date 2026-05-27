# pip install pyzipper tqdm
import os, sys, getpass, pyzipper, datetime, tqdm, argparse

EXCLUDE_EXT = {'.zip'}
ap = argparse.ArgumentParser()
ap.add_argument('data_root')
args = ap.parse_args()

src = args.data_root
pw = getpass.getpass("Password: ").encode()
out = src.rstrip('/\\') + '_' + datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S') + '.zip'

with pyzipper.AESZipFile(out, 'w', compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as z:
    z.setpassword(pw)
    for root, _, files in tqdm.tqdm(os.walk(src), position=0):
        for f in tqdm.tqdm(files, position=1, leave=False):
            if os.path.splitext(f)[1].lower() not in EXCLUDE_EXT:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, src))
