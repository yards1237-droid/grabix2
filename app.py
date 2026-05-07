from flask import Flask, request, Response, send_from_directory, jsonify
from flask_cors import CORS
import yt_dlp, tempfile, os, logging, subprocess, sys

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
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
    tmp.write(cookies_content)
    tmp.close()
    return tmp.name

def get_base_opts():
    opts = {
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
    }
    cookie_file = write_cookies()
    if cookie_file:
        opts['cookiefile'] = cookie_file
    return opts

@app.route('/info', methods=['POST'])
def info():
    url = (request.get_json() or {}).get('url','').strip()
    if not url: return jsonify({'error':'No URL'}), 400
    try:
        opts = get_base_opts()
        opts['skip_download'] = True
        with yt_dlp.YoutubeDL(opts) as ydl:
            i = ydl.extract_info(url, download=False)
            return jsonify({
                'title': i.get('title','Video'),
                'thumbnail': i.get('thumbnail',''),
                'site': i.get('extractor_key','Unknown'),
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/ytdl', methods=['POST'])
def ytdl():
    """YouTube specific download endpoint - tries multiple methods"""
    data = request.get_json() or {}
    url     = data.get('url','').strip()
    quality = data.get('quality', '720')
    if not url: return jsonify({'error':'No URL'}), 400

    # Try multiple player clients
    clients = ['android_creator', 'ios', 'android', 'web_creator']
    
    for client in clients:
        try:
            opts = get_base_opts()
            opts['skip_download'] = True
            opts['extractor_args'] = {'youtube': {'player_client': [client]}}
            
            if quality in ('max', 'auto'):
                fmt = 'best[ext=mp4]/best'
            else:
                fmt = f'best[height<={quality}][ext=mp4]/best[height<={quality}]/best'
            
            opts['format'] = fmt

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'video')
                
                # Get direct URL
                if 'url' in info:
                    direct_url = info['url']
                elif 'formats' in info:
                    formats = [f for f in info['formats'] if f.get('url')]
                    mp4 = [f for f in formats if f.get('ext') == 'mp4' and f.get('url')]
                    if quality not in ('max', 'auto'):
                        mp4 = [f for f in mp4 if f.get('height', 999) <= int(quality)]
                    direct_url = (mp4 or formats)[-1]['url'] if (mp4 or formats) else None
                else:
                    continue

                if not direct_url:
                    continue

                return jsonify({
                    'title': title,
                    'download_url': f'/proxy?url={yt_dlp.utils.urllib.parse.quote(direct_url)}&title={yt_dlp.utils.urllib.parse.quote(title)}',
                    'client_used': client
                })
        except Exception as e:
            continue

    return jsonify({'error': 'YouTube is blocking this server. Try a different video or platform.'}), 400

@app.route('/proxy')
def proxy():
    """Proxy the video download to avoid CORS issues"""
    import urllib.request
    import urllib.parse
    
    video_url = request.args.get('url','')
    title     = request.args.get('title', 'video')
    
    if not video_url:
        return jsonify({'error': 'No URL'}), 400

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.youtube.com/',
        }
        req = urllib.request.Request(video_url, headers=headers)
        
        def generate():
            with urllib.request.urlopen(req, timeout=30) as response:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    yield chunk

        safe_title = ''.join(c for c in title if c.isalnum() or c in ' -_').strip()[:60]
        return Response(
            generate(),
            mimetype='video/mp4',
            headers={
                'Content-Disposition': f'attachment; filename="{safe_title}.mp4"',
                'Cache-Control': 'no-cache',
            }
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['GET','POST'])
def download():
    if request.method == 'POST':
        d = request.get_json() or {}
        url, quality, fmt = d.get('url','').strip(), d.get('quality','max'), d.get('format','auto')
    else:
        url, quality, fmt = request.args.get('url','').strip(), request.args.get('quality','max'), request.args.get('format','auto')
    if not url: return jsonify({'error':'No URL'}), 400
    try:
        opts = get_base_opts()
        opts['skip_download'] = True
        opts['format'] = 'best[ext=mp4]/best' if quality in ('max','auto') else f'best[height<={quality}][ext=mp4]/best'
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title','video')
            if 'url' in info:
                direct_url = info['url']
            elif 'formats' in info:
                formats = [f for f in info['formats'] if f.get('url')]
                mp4 = [f for f in formats if f.get('ext') == 'mp4']
                direct_url = (mp4 or formats)[-1]['url']
            else:
                return jsonify({'error':'No URL'}), 400
            safe = ''.join(c for c in title if c.isalnum() or c in ' -_').strip()[:60]
            return jsonify({'direct_url': direct_url, 'filename': safe + '.mp4', 'title': title})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/debug')
def debug():
    cookies = os.environ.get('YOUTUBE_COOKIES', '')
    return jsonify({'cookies_length': len(cookies), 'has_cookies': bool(cookies)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
