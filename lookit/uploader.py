import os
import sys
import gtk
import ftplib
import pynotify
import shutil
import socket
import tempfile
import time
import urllib.request, urllib.parse, urllib.error
import urllib.parse

PROTO_LIST = ['None']

try:
	import ftplib
	PROTO_LIST.append('FTP')
except ImportError:
	print('FTP support not found')

try:
	import paramiko
	PROTO_LIST.append('SSH')
except ImportError:
	print('SFTP support not found')

try:
	import ubuntuone
	import ubuntuone.storageprotocol
	# PROTO_LIST.append('Ubuntu One') # Not yet supported
except ImportError:
	print('Ubuntu One support not found')

try:
    from . import imgur
    PROTO_LIST.append('Imgur')
except ImportError:
    print('Imgur support not available')

try:
	import pycurl
	import re
	PROTO_LIST.append('Omploader')
except ImportError:
	print('Omploader support not available')

try:
    import cloud
    if cloud.POSTER and cloud.ORDERED_DICT:
        PROTO_LIST.append('CloudApp')
    else:
        print('CloudApp support not available')
except ImportError:
    print('CloudApp support not available')

from . import liblookit
from . import lookitconfig

class OmploaderUploader:
	def __init__(self):
		self.response = ''
		self.mapping = {}

	def curl_response(self, buf):
		self.response = self.response + buf

	def upload(self, image):
		c = pycurl.Curl()
		values = [	('file1', (c.FORM_FILE, image))]
		c.setopt(c.URL, 'http://ompldr.org/upload')
		c.setopt(c.HTTPPOST, values)
		c.setopt(c.WRITEFUNCTION, self.curl_response)

		c.perform()
		c.close()

		m = re.findall("v\w+", self.response)
		self.mapping['original_image'] = "http://ompldr.org/%s" % m[2]

def get_proto_list():
	return PROTO_LIST

def upload_file_ftp(f, hostname, port, username, password, directory, url):
	i = open(f, 'rb')

	try:
		ftp = ftplib.FTP()
		ftp.connect(hostname, port)
		ftp.login(username, password)
		ftp.cwd(directory)
		ftp.storbinary('STOR ' + os.path.basename(f), i)
		ftp.quit()
	except Exception as error:
		return False, 'Error occured during FTP upload'

	i.close()

	return True, None

def upload_file_sftp(f, hostname, port, username, password, directory, url):
    try:
        t = paramiko.Transport((hostname, port))
        t.connect(username=username, password=password)
        sftp = paramiko.SFTPClient.from_transport(t)
        sftp.chdir(directory)
        sftp.put(f, os.path.basename(f))
    except socket.gaierror:
        return False, 'Name or service not known'
    except paramiko.AuthenticationException:
        return False, 'Authentication failed'
    except IOError:
        return False, 'Destination directory does not exist'
    return True, None

def upload_file_omploader(f):
	if not 'Omploader' in PROTO_LIST:
		print('Error: Omploader not supported')
	i = OmploaderUploader()
	i.upload(f)
	if not 'error_msg' in i.mapping:
		return True, i.mapping
	else:
		return False, i.mapping.get('error_msg')

def upload_file_imgur(f):
	if not 'Imgur' in PROTO_LIST:
		print('Error: Imgur not supported')
	i = imgur.ImgurUploader()
	i.upload(f)
	if not 'error_msg' in i.mapping:
		return True, i.mapping
	else:
		return False, i.mapping.get('error_msg')

def upload_file_cloud(f, username, password):
    if not 'CloudApp' in PROTO_LIST:
        print('Error: CloudApp not supported')
    try:
        mycloud = cloud.Cloud()
        mycloud.auth(username, password)
        result = mycloud.upload_file(f)
        data = {'original_image': result['url']}
        return True, data
    except cloud.CloudException as e:
        return False, e.message

def upload_pixbuf(pb):
    if pb is not None:
        ftmp = tempfile.NamedTemporaryFile(suffix='.png', prefix='', delete=False)
        pb.save_to_callback(ftmp.write, 'png')
        ftmp.flush()
        ftmp.close()
        upload_file(ftmp.name)

def upload_file(image, existing_file=False):
    config = lookitconfig.LookitConfig()

    proto = config.get('Upload', 'type')

    if proto == 'SSH':
        liblookit.show_notification('Lookit', 'Uploading image to {0}...'.format(config.get('Upload', 'hostname')))
        success, data = upload_file_sftp(image,
                    config.get('Upload', 'hostname'),
                    int(config.get('Upload', 'port')),
                    config.get('Upload', 'username'),
                    config.get('Upload', 'password'),
                    config.get('Upload', 'directory'),
                    config.get('Upload', 'url'),
                    )
    elif proto == 'FTP':
        liblookit.show_notification('Lookit', 'Uploading image to {0}...'.format(config.get('Upload', 'hostname')))
        success, data = upload_file_ftp(image,
                    config.get('Upload', 'hostname'),
                    int(config.get('Upload', 'port')),
                    config.get('Upload', 'username'),
                    config.get('Upload', 'password'),
                    config.get('Upload', 'directory'),
                    config.get('Upload', 'url'),
                    )
    elif proto == 'Omploader':
        liblookit.show_notification('Lookit', 'Uploading image to Omploader...')
        success, data = upload_file_omploader(image)
        try:
            f = open(liblookit.LOG_FILE, 'ab')
            f.write(time.ctime() + ' Uploaded screenshot to Omploader: ' + data['original_image'] + '\n')
        except IOError as e:
            pass
        finally:
            f.close()
    elif proto == 'Imgur':
        liblookit.show_notification('Lookit', 'Uploading image to Imgur...')
        success, data = upload_file_imgur(image)
        try:
            f = open(liblookit.LOG_FILE, 'ab')
            f.write(time.ctime() + ' Uploaded screenshot to Imgur: ' + data['original_image'] + '\n')
            f.write('Delete url: ' + data['delete_page'] + '\n')
        except IOError as e:
            pass
        finally:
            f.close()
    elif proto == 'CloudApp':
        liblookit.show_notification('Lookit', 'Uploading image to CloudApp...')
        success, data = upload_file_cloud(image,
                    config.get('Upload', 'username'),
                    config.get('Upload', 'password'))
    elif proto == 'None':
        success = True
        data = False
    else:
        success = False
        data = "Error: no such protocol: {0}".format(proto)

    if not success:
        liblookit.show_notification('Lookit', 'Error: ' + data)
        return

    if data:
        url = data['original_image']
    else:
        url = urllib.parse.urljoin(config.get('Upload', 'url'),
            os.path.basename(image))

    if config.getboolean('General', 'shortenurl') and proto != None:
        url = urllib.request.urlopen('http://is.gd/api.php?longurl={0}'
                        .format(url)).readline()
    if not existing_file:
        if config.getboolean('General', 'trash'):
            os.remove(os.path.abspath(image))
        else:
            try:
                timestamp = time.strftime('%Y-%m-%d_%H-%M-%S')
                filename = timestamp + '.png'
                destination = os.path.join(config.get('General', 'savedir'), filename)
                i = 0
                while os.path.exists(destination):
                    filename = timestamp + '_' + str(i) + '.png'
                    destination = os.path.join(config.get('General', 'savedir'), filename)
                    i += 1
                shutil.move(image, destination)
                image = destination
            except IOError:
                print('Error moving file')

    clipboard = gtk.clipboard_get()
    clipboard.set_text(url)
    clipboard.store()

    if proto == 'None':
        if config.getboolean('General', 'trash'):
            liblookit.show_notification('Lookit', 'Error: No upload type selected')
        else:
            liblookit.show_notification('Lookit', 'Image saved: ' + image)
    else:
        liblookit.show_notification('Lookit', 'Upload complete: ' + url)

