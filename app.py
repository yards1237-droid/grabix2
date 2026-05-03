from flask import Flask, request, Response, send_from_directory, jsonify
from flask_cors import CORS
import yt_dlp, tempfile, os, logging

app = Flask(__name__)
app.static_folder = None
CORS(app)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/style.css')
def css():
    return send_from_directory('.', 'style.css')

@app.route('/script.js')
def js():
    return send_from_directory('.', 'clean_script.js')

def write_cookies():
    cookies_content = os.environ.get('YOUTUBE_COOKIES', '')
    if not cookies_content:
        return None
    # Write raw to file
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
    tmp.write(cookies_content)
    tmp.close()
    return tmp.name

def get_ydl_opts(extra={}):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
        # Use Android client - most reliable bypass
        'extractor_args': {
            'youtube': {
                'player_client': ['android_creator'],
            }
        },
    }
    cookie_file = write_cookies()
    if cookie_file:
        opts['cookiefile'] = cookie_file
    opts.update(extra)
    return opts

@app.route('/info', methods=['POST'])
def info():
    url = (request.get_json() or {}).get('url','').strip()
    if not url: return jsonify({'error':'No URL'}), 400
    try:
        opts = get_ydl_opts({'skip_download': True})
        with yt_dlp.YoutubeDL(opts) as ydl:
            i = ydl.extract_info(url, download=False)
            return jsonify({
                'title': i.get('title','Video'),
                'thumbnail': i.get('thumbnail',''),
                'site': i.get('extractor_key','Unknown'),
                'uploader': i.get('uploader','')
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/download', methods=['GET','POST'])
def download():
    if request.method == 'POST':
        d = request.get_json() or {}
        url, quality, fmt = d.get('url','').strip(), d.get('quality','max'), d.get('format','auto')
    else:
        url, quality, fmt = request.args.get('url','').strip(), request.args.get('quality','max'), request.args.get('format','auto')

    if not url: return jsonify({'error':'No URL'}), 400

    try:
        if fmt == 'mp3':
            fmt_str = 'bestaudio/best'
        else:
            fmt_str = 'best[ext=mp4]/best' if quality in ('max','auto') else f'best[height<={quality}][ext=mp4]/best[height<={quality}]'

        opts = get_ydl_opts({'skip_download': True, 'format': fmt_str})

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

            if 'url' in info:
                direct_url = info['url']
            elif 'formats' in info:
                formats = [f for f in info['formats'] if f.get('url')]
                mp4 = [f for f in formats if f.get('ext') == 'mp4']
                direct_url = (mp4 or formats)[-1]['url']
            else:
                return jsonify({'error': 'No URL found'}), 400

            title = info.get('title', 'video')
            safe = ''.join(c for c in title if c.isalnum() or c in ' -_').strip()[:60]

            return jsonify({
                'direct_url': direct_url,
                'filename': safe + '.mp4',
                'title': title
            })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/debug')
def debug():
    """Check if cookies are loaded"""
    cookies = os.environ.get('YOUTUBE_COOKIES', '')
    cookie_file = write_cookies()
    lines = 0
    if cookie_file:
        with open(cookie_file) as f:
            lines = len(f.readlines())
    return jsonify({
        'cookies_env_length': len(cookies),
        'cookie_file_lines': lines,
        'first_100_chars': cookies[:100],
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
