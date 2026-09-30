#!/usr/bin/env python3
"""Dependency-free structural checks; never a substitute for research or browser QA."""
import argparse
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

def site_fingerprint(root):
    """Bind review to rendered source/assets; exclude review and instruction files."""
    root = Path(root).resolve()
    excluded = {'.git', '.qa', 'reviews', 'node_modules', 'factory-guide', 'skills', 'reference-original'}
    extensions = {'.html', '.css', '.js', '.mjs', '.json', '.geojson', '.topojson', '.csv', '.tsv',
                  '.svg', '.jpg', '.jpeg', '.png', '.webp', '.avif', '.gif', '.ico',
                  '.woff', '.woff2', '.ttf', '.otf', '.mp4', '.webm', '.mp3', '.wav'}
    records = {'project.json', 'assets.json', 'evidence.json', 'qa.json', 'visual-review.json'}
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if relative.as_posix() in records:
            continue
        if path.is_file() and not excluded.intersection(relative.parts) and path.suffix.lower() in extensions:
            if root not in path.resolve().parents:
                raise ValueError('أصل خارج مجلد المشروع: '+relative.as_posix())
            digest.update(relative.as_posix().encode('utf-8')+b'\0')
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()

class Page(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=[];self.refs=[];self.links=[];self.images=[];self.lang='';self.direction='';self.h1=0;self.errors=[];self.draft=False;self.meta={}
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='html':self.lang=a.get('lang','');self.direction=a.get('dir','')
        if tag=='h1':self.h1+=1
        if 'id' in a:self.ids.append(a['id'])
        if 'data-draft' in a:self.draft=True
        if tag=='meta':self.meta[a.get('property',a.get('name',''))]=a.get('content','')
        if tag=='img':
            self.images.append(a.get('src',''))
            if 'alt' not in a:self.errors.append('صورة بلا alt: '+a.get('src',''))
        if tag=='a' and a.get('href'):self.links.append(a['href'])
        if tag=='a' and a.get('target')=='_blank' and not {'noopener','noreferrer'}.issubset(set(a.get('rel','').split())):self.errors.append('رابط خارجي بلا حماية rel: '+a.get('href',''))
        for key in ('href','src'):
            if a.get(key):self.refs.append(a[key])
        if a.get('srcset'):
            candidates=[item.strip().split()[0] for item in a['srcset'].split(',') if item.strip()]
            self.refs.extend(candidates)
            if tag=='img':self.images.extend(candidates)
        for key in ('aria-controls','aria-labelledby','aria-describedby'):
            self.refs.extend('#'+v for v in a.get(key,'').split())
    handle_startendtag=handle_starttag

def inspect(root,release=False):
    root=Path(root).resolve();errors=[];warnings=[]
    def load(name):
        path=root/name
        if not path.is_file():errors.append('ملف مطلوب مفقود: '+name);return {}
        try:return json.loads(path.read_text(encoding='utf-8'))
        except (ValueError,OSError):errors.append('JSON غير صالح: '+name);return {}
    config=load('project.json');evidence=load('evidence.json');assets=load('assets.json');qa=load('qa.json')
    visual=load('visual-review.json') if release or (root/'visual-review.json').is_file() else {}
    if not (root/'index.html').is_file():return ['index.html مفقود'],warnings
    pages={}
    for path in root.glob('*.html'):
        p=Page();p.feed(path.read_text(encoding='utf-8'));pages[path.name]=p
        errors.extend(f'{path.name}: {e}' for e in p.errors)
        if not p.lang.startswith('ar') or p.direction!='rtl':errors.append(f'{path.name}: lang/dir غير صحيحين')
        if p.h1!=1:errors.append(f'{path.name}: يجب وجود h1 واحد')
        if len(p.ids)!=len(set(p.ids)):errors.append(f'{path.name}: معرفات id مكررة')
        if release and p.draft:errors.append(f'{path.name}: علامة المسودة data-draft باقية')
    def local_ref(ref,base,ids=None):
        if ref.startswith(('mailto:','tel:','data:')):return
        parts=urlsplit(ref)
        if parts.scheme in ('http','https'):return
        if parts.scheme or ref.startswith('//'):errors.append('رابط غير مسموح أو مطلق: '+ref);return
        if parts.path.startswith('/'):errors.append('مسار محلي مطلق: '+ref);return
        dest=(base/unquote(parts.path)).resolve() if parts.path else base
        if parts.path:
            if dest!=root and root not in dest.parents:errors.append('مرجع خارج مجلد المشروع: '+ref);return
            if not dest.exists():errors.append('مرجع محلي مفقود: '+ref);return
        fragment=unquote(parts.fragment)
        if fragment:
            target_ids=ids
            if parts.path and dest.suffix=='.html':
                p=Page();p.feed(dest.read_text(encoding='utf-8'));target_ids=p.ids
            if target_ids is not None and fragment not in target_ids:errors.append('هدف رابط غير موجود: '+ref)
    for filename,p in pages.items():
        for ref in p.refs:local_ref(ref,root,p.ids)
    css='';css_images=[]
    for path in root.glob('*.css'):
        text=path.read_text(encoding='utf-8');css+=text
        for ref in re.findall(r'url\([\s\'"]*([^\)\'"\s]+)',text):
            local_ref(ref,path.parent)
            parts=urlsplit(ref)
            if not parts.scheme and not ref.startswith('//') and Path(parts.path).suffix.lower() in ('.jpg','.jpeg','.png','.webp','.avif'):
                dest=(path.parent/unquote(parts.path)).resolve()
                if root in dest.parents:css_images.append(dest.relative_to(root).as_posix())
    if 'prefers-reduced-motion' not in css:errors.append('لا معالجة للحركة المخففة')
    if config.get('features',{}).get('print') and not re.search(r'@media\s+print',css):errors.append('الطباعة مفعّلة بلا تنسيق print')
    if not config.get('name') or not config.get('recipe') or not config.get('style'):errors.append('هوية المشروع غير مكتملة')
    listed=set();asset_by_path={}
    for asset in assets.get('assets',[]):
        if not isinstance(asset,dict):errors.append('سجل أصل غير صالح');continue
        path=asset.get('path','');listed.add(path);asset_by_path[path]=asset
        if not path or not asset.get('rights') or not asset.get('source'):errors.append('بيانات أصل غير مكتملة: '+path)
        if path:local_ref(path,root)
        if asset.get('kind')=='generated' and not asset.get('caption'):errors.append('صورة مولّدة بلا تسمية: '+path)
    for p in pages.values():
        for image in p.images:
            if image and not image.startswith(('http:','https:','data:')) and image not in listed:errors.append('صورة بلا سجل حقوق ومصدر: '+image)
    for image in css_images:
        if image not in listed:errors.append('صورة CSS بلا سجل حقوق ومصدر: '+image)
    for image in [image for p in pages.values() for image in p.images]+css_images:
        if release and image and Path(urlsplit(image).path).suffix.lower() in ('.jpg','.jpeg','.png','.webp','.avif'):
            audit=asset_by_path.get(image,{}).get('visual_review',{})
            if (audit.get('status')!='confirmed' or not all(str(audit.get(k,'')).strip() for k in ('depicts','placement_reason','caption_match_note','checked_at'))):
                errors.append('مراجعة مطابقة الصورة ناقصة: '+image)
    imagefiles=[p for p in root.rglob('*') if p.suffix.lower() in ('.jpg','.jpeg','.png','.webp','.avif') and not any(x in p.parts for x in ('.git','.qa','node_modules','reviews'))]
    total=sum(p.stat().st_size for p in imagefiles)/1024
    if total>config.get('image_budget_kb',4096):warnings.append(f'مجموع الصور {total:.0f}KB يتجاوز الميزانية')
    for path in imagefiles:
        limit=800 if any(s in path.name.lower() for s in ('hero','cover')) else 500
        if path.stat().st_size/1024>limit:warnings.append(f'صورة كبيرة: {path.relative_to(root)}')
    claim_ids=[]
    for claim in evidence.get('claims',[]):
        if not isinstance(claim,dict):errors.append('سجل ادعاء غير صالح');continue
        claim_ids.append(claim.get('id',''))
        if not claim.get('id') or not claim.get('text'):errors.append('ادعاء بلا معرف أو نص')
        state=claim.get('status')
        if state not in ('verified','source-reported','analysis','user-provided','needs-verification'):errors.append('حالة دليل غير معروفة')
        if state in ('verified','source-reported'):
            u=urlsplit(claim.get('source_url',''))
            if u.scheme not in ('http','https') or not u.netloc or not claim.get('source_title') or not claim.get('checked_at'):errors.append('مصدر ادعاء غير مكتمل: '+claim.get('id',''))
            if release:
                if u.path in ('','/') and not u.query:errors.append('رابط مصدر عام لا يحدد المادة: '+claim.get('id',''))
                if claim.get('source_url','') not in pages['index.html'].links:errors.append('رابط المصدر غير ظاهر للقارئ: '+claim.get('id',''))
        if release:
            if state=='needs-verification':errors.append('ادعاء يحتاج تحققاً: '+claim.get('id',''))
            if not claim.get('locator') or claim['locator'] not in pages['index.html'].ids:errors.append('موضع استشهاد غير موجود: '+claim.get('id',''))
    if len(claim_ids)!=len(set(claim_ids)):errors.append('معرفات أدلة مكررة')
    if release:
        concept=visual.get('concept',{})
        if not all(str(concept.get(k,'')).strip() for k in ('idea','why_this_subject','hero_decision','signature_moment')):
            errors.append('الفكرة والإخراج البصري غير مكتملين في visual-review.json')
        beats=visual.get('beats',[])
        if len(beats)<2 or any(not isinstance(b,dict) or not all(str(b.get(k,'')).strip() for k in ('section','reader_change','visual_change')) for b in beats):
            errors.append('تغير المشاهد غير موثق في visual-review.json')
        elif len({b['visual_change'].strip() for b in beats})<2:
            errors.append('تغير المشاهد مكرر في visual-review.json')
        screenshots=visual.get('screenshots',{})
        for label in ('desktop','mobile'):
            relative=screenshots.get(label,'')
            shot=(root/relative).resolve() if relative else root
            if (not relative or Path(relative).parts[:1]!=('reviews',) or
                shot!=root and root not in shot.parents or not shot.is_file() or
                shot.suffix.lower() not in ('.png','.jpg','.jpeg','.webp') or
                not shot.read_bytes()[:12].startswith((b'\x89PNG\r\n\x1a\n',b'\xff\xd8\xff',b'RIFF'))):
                errors.append('لقطة صفحة منفذة مفقودة أو غير صالحة: '+label)
        review=visual.get('review',{})
        if review.get('build_fingerprint') != site_fingerprint(root):
            errors.append('بصمة المراجعة غائبة أو لا تطابق نسخة الصفحة؛ راجع التغييرات قبل تجديدها')
        if (review.get('status')!='pass' or not all(str(review.get(k,'')).strip() for k in ('note','revisions','checked_at'))):
            errors.append('مشاهدة التصميم ومراجعته غير مكتملتين')
        if config.get('status')!='ready':errors.append('المشروع لم يُعلن ready بعد مراجعة فعلية')
        scope=config.get('content_scope')
        if scope not in ('factual','analysis','original-nonfactual'):errors.append('content_scope غير محسوم')
        if scope in ('factual','analysis') and not evidence.get('claims'):errors.append('المادة الواقعية/التحليلية بلا سجل أدلة')
        url=config.get('published_url','');u=urlsplit(url)
        if u.scheme!='https' or not u.netloc:errors.append('رابط نشر HTTPS النهائي غير محدد')
        for key in ('og:title','og:description','og:image','og:url'):
            if not pages['index.html'].meta.get(key):errors.append('بطاقة مشاركة ناقصة: '+key)
        og=urlsplit(pages['index.html'].meta.get('og:image',''))
        if og.scheme!='https' or not og.netloc:errors.append('og:image يجب أن يكون رابط HTTPS مطلقاً')
        required=('desktop','mobile375','tablet768','keyboard','reduced_motion','no_javascript','core_flow','sources','print')
        for name in required:
            check=qa.get('checks',{}).get(name,{})
            allowed_na=(name=='sources' and scope=='original-nonfactual') or (name=='print' and not config.get('features',{}).get('print'))
            state=check.get('status')
            if not (state=='pass' or (state=='not-applicable' and allowed_na)) or not check.get('note','').strip():errors.append('تحقق يدوي غير مكتمل: '+name)
        if warnings:errors.extend('ميزانية تحتاج معالجة قبل النشر: '+w for w in warnings)
    else:
        if config.get('status')=='draft':warnings.append('المسودة صالحة للبدء فقط؛ ليست جاهزة للنشر')
    # Ignore OS metadata: it is not page content and must not masquerade as a design failure.
    return list(dict.fromkeys(errors)),list(dict.fromkeys(warnings))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('project',type=Path);parser.add_argument('--release',action='store_true');parser.add_argument('--json',action='store_true');parser.add_argument('--fingerprint',action='store_true',help='Print the current page/assets fingerprint; does not record or approve a review')
    args=parser.parse_args()
    if args.fingerprint:
        if not (args.project/'index.html').is_file():
            parser.error('مجلد المشروع لا يحتوي index.html')
        try: print(site_fingerprint(args.project))
        except (OSError, ValueError) as error: parser.exit(1, str(error)+'\n')
        return 0
    try:errors,warnings=inspect(args.project,args.release)
    except (OSError,ValueError,TypeError,KeyError) as error:errors=['تعذر الفحص: '+str(error)];warnings=[]
    result={'mode':'release' if args.release else 'draft','passed':not errors,'errors':errors,'warnings':warnings}
    if args.json:print(json.dumps(result,ensure_ascii=False,indent=2))
    else:
        for error in errors:print('FAIL '+error)
        for warning in warnings:print('NOTE '+warning)
        print(('PASS' if not errors else 'FAIL')+' · '+result['mode']+(' (فحص بنيوي؛ لا يمنح درجة تصميم)' if args.release else ''))
    return 1 if errors else 0
if __name__=='__main__':raise SystemExit(main())
