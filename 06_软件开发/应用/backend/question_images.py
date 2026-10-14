"""Read-only image overlays. Viewing a source picture never grants eligibility."""
import json, pathlib, threading

class ImageCatalogue:
    def __init__(self, app_dir):
        self.root = pathlib.Path(app_dir) / 'assets/question-images'
        self.path = self.root / 'index.json'
        self.stamp = None; self.data = {}; self.lock = threading.Lock()

    def load(self):
        if not self.path.exists(): return {}
        stamp = self.path.stat().st_mtime_ns
        with self.lock:
            if self.stamp != stamp:
                self.data = json.loads(self.path.read_text('utf-8')); self.stamp = stamp
        return self.data

    def entry(self, q):
        entry = self.load().get('questions', {}).get(q['id'])
        if not entry: return None
        refs = q.get('source_assets', {}).get('question', [])
        signature = [[r['file'], r['pdf_page'], r.get('pdf_sha256', '')] for r in refs]
        return entry if signature == entry['source_signature'] else None

    def decorate(self, q):
        q = dict(q); entry = self.entry(q)
        q['image_ready'] = bool(entry and entry.get('question_images'))
        q['body_display_mode'] = 'text'
        if not q['image_ready']: return q
        for field in ('question_images', 'reference_images', 'answer_images'):
            q[field] = entry[field]
        q['image_mode'] = entry['mode']; q['image_status'] = entry['status']
        q['image_layout_issue'] = entry.get('layout_issue', '')
        if not q.get('source_body_ready') or not q.get('render_ready'):
            q['body_display_mode'] = 'image'
        return q

    def file(self, name):
        if not name or '/' in name or '\\' in name or name not in self.load().get('files', {}): raise KeyError('题图不存在')
        path = (self.root / name).resolve()
        if not path.is_relative_to(self.root.resolve()) or path.suffix != '.webp' or not path.is_file(): raise KeyError('题图不存在')
        return path
