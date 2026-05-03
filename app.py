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

@app.route('/info', methods=['POST'])
def info():
    url = (request.get_json() or {}).get('url','').strip()
    if not url: return jsonify({'error':'No URL'}), 400
    try:
        with yt_dlp.YoutubeDL({'quiet':True,'skip_download':True,'no_warnings':True}) as ydl:
            i = ydl.extract_info(url, download=False)
            return jsonify({'title':i.get('title','Video'),'thumbnail':i.get('thumbnail',''),'site':i.get('extractor_key','Unknown')})
    except Exception as e:
        return jsonify({'error':str(e)}), 400

@app.route('/download', methods=['GET','POST'])
def download():
    if request.method == 'POST':
        d = request.get_json() or {}
        url,quality,fmt = d.get('url','').strip(),d.get('quality','max'),d.get('format','auto')
    else:
        url,quality,fmt = request.args.get('url','').strip(),request.args.get('quality','max'),request.args.get('format','auto')
    if not url: return jsonify({'error':'No URL'}),400
    tmpdir = tempfile.mkdtemp()
    out = os.path.join(tmpdir,'%(title)s.%(ext)s')
    if fmt=='mp3':
        opts={'format':'bestaudio/best','outtmpl':out,'postprocessors':[{'key':'FFmpegExtractAudio','preferredcodec':'mp3'}],'quiet':True,'no_warnings':True}
    else:
        fs='bestvideo+bestaudio/best' if quality in('max','auto') else f'bestvideo[height<={quality}]+bestaudio/best'
        opts={'format':fs,'outtmpl':out,'merge_output_format':'mp4','quiet':True,'no_warnings':True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info=ydl.extract_info(url,download=True)
            title=info.get('title','video')
        files=os.listdir(tmpdir)
        if not files: return jsonify({'error':'No file'}),500
        fp=os.path.join(tmpdir,files[0])
        ext=files[0].split('.')[-1]
        def gen():
            with open(fp,'rb') as f:
                while True:
                    c=f.read(65536)
                    if not c: break
                    yield c
            try: os.remove(fp);os.rmdir(tmpdir)
            except: pass
        safe=''.join(c for c in title if c.isalnum() or c in ' -_').strip()[:60]
        return Response(gen(),mimetype='application/octet-stream',
                        headers={'Content-Disposition':f'attachment; filename="{safe}.{ext}"'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

if __name__=='__main__':
    app.run(host='0.0.0.0',port=10000)
