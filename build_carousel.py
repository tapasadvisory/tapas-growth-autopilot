#!/usr/bin/env python3
"""Build the TAPAS Growth Autopilot LinkedIn carousel to Ram's production standard.
1080x1350 (4:5), master palette only, official logo every slide, Ram photo on
cover + closing, TAPAS Advisory watermark, closing byline + diagnostic."""
import math, os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1080, 1350
OUT = os.path.expanduser("~/workspace/goals/raise-tapas-advisory-s-market-authority-and-visibility/files/github-autopilot-carousel")
os.makedirs(OUT, exist_ok=True)

NAVY=(0,31,122); ROYAL=(13,75,255); CYAN=(20,184,230); PURPLE=(106,0,255); VIOLET=(143,31,255)
GOLD=(184,134,11); BRONZE=(199,154,43); TEAL=(0,143,143); INDIGO=(47,47,212); SLATE=(74,85,104); WHITE=(255,255,255)

FB="/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
FR="/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
FS="/usr/share/fonts/truetype/noto/NotoSans-SemiBold.ttf"
def font(p,s): return ImageFont.truetype(p,s)

LOGO = Image.open(os.path.expanduser("~/workspace/user/logo-changereadyx.png")).convert("RGB")
PHOTO = Image.open(os.path.expanduser("~/workspace/profile-images/user-profile-reference.jpg")).convert("RGB")

def gradient():
    img = Image.new("RGB",(W,H))
    px = img.load()
    stops=[(0.0,NAVY),(0.55,INDIGO),(1.0,ROYAL)]
    for y in range(H):
        t=y/(H-1)
        for i in range(len(stops)-1):
            t0,c0=stops[i]; t1,c1=stops[i+1]
            if t0<=t<=t1:
                f=(t-t0)/(t1-t0)
                col=tuple(int(c0[k]+(c1[k]-c0[k])*f) for k in range(3)); break
        for x in range(W): px[x,y]=col
    glow=Image.new("RGB",(W,H),(0,0,0)); gd=ImageDraw.Draw(glow)
    gd.ellipse([-350,H-520,W+150,H+260],fill=(40,20,90))
    glow=glow.filter(ImageFilter.GaussianBlur(180))
    from PIL import ImageChops
    img=ImageChops.add(img,glow)
    return img

def watermark(img):
    ov=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(ov)
    f=font(FB,118)
    for yy in (-60, 400, 860):
        d.text((40,yy),"TAPAS ADVISORY   TAPAS ADVISORY",font=f,fill=(255,255,255,26))
    ov=ov.rotate(-28, resample=Image.BICUBIC, center=(W//2,H//2))
    base=img.convert("RGBA"); base.alpha_composite(ov)
    img.paste(base.convert("RGB"),(0,0))

def wrap(d,text,f,maxw):
    lines=[]
    for para in text.split("\n"):
        if not para.strip():
            lines.append(""); continue
        cur=""
        for w_ in para.split():
            t=(cur+" "+w_).strip()
            if d.textlength(t,font=f)<=maxw: cur=t
            else: lines.append(cur); cur=w_
        if cur: lines.append(cur)
    return lines

def logo_chip(img):
    chip_w=170; chip_h=170
    chip=Image.new("RGB",(chip_w,chip_h),WHITE)
    lg=LOGO.resize((150,150))
    chip.paste(lg,(10,10))
    img.paste(chip,(48,44))
    d=ImageDraw.Draw(img)
    d.rounded_rectangle([48,44,48+chip_w-1,44+chip_h-1],radius=18,outline=BRONZE,width=4)

def footer(img,n,total=8):
    d=ImageDraw.Draw(img)
    d.text((48,H-72),"TAPAS GROWTH AUTOPILOT · TAPAS ADVISORY",font=font(FS,24),fill=(210,220,255))
    s=f"{n} / {total}"; tw=d.textlength(s,font=font(FS,24))
    d.text((W-48-tw,H-72),s,font=font(FS,24),fill=(210,220,255))

def photo_circle(img,cx,cy,r):
    ph=PHOTO.resize((r*2,r*2),Image.LANCZOS)
    mask=Image.new("L",(r*2,r*2),0); md=ImageDraw.Draw(mask); md.ellipse([0,0,r*2,r*2],fill=255)
    img.paste(ph,(cx-r,cy-r),mask)
    d=ImageDraw.Draw(img); d.ellipse([cx-r,cy-r,cx+r,cy+r],outline=GOLD,width=10)

def content_slide(n,kicker,headline,body,stat=None):
    img=gradient(); logo_chip(img); watermark(img)
    d=ImageDraw.Draw(img)
    d.text((48,268),kicker,font=font(FB,30),fill=BRONZE)
    y=330
    for ln in wrap(d,headline,font(FB,74),W-96):
        d.text((48,y),ln,font=font(FB,74),fill=WHITE); y+=92
    y+=26
    for ln in wrap(d,body,font(FR,41),W-96):
        d.text((48,y),ln,font=font(FR,41),fill=(226,233,255)); y+=58
    if stat:
        y+=30; d.line([48,y,W-48,y],fill=CYAN,width=3); y+=36
        for ln in wrap(d,stat,font(FB,44),W-96):
            d.text((48,y),ln,font=font(FB,44),fill=CYAN); y+=56
    footer(img,n)
    return img

slides=[]
# 1 COVER
img=gradient(); logo_chip(img); watermark(img); d=ImageDraw.Draw(img)
d.text((48,268),"TAPAS ADVISORY · OPEN SOURCE",font=font(FB,30),fill=BRONZE)
y=330
for ln in wrap(d,"I built my own growth engine.",font(FB,80),W-96):
    d.text((48,y),ln,font=font(FB,80),fill=WHITE); y+=100
y+=14
for ln in wrap(d,"Because I refused to hand my accounts to another SaaS.",font(FR,42),W-96):
    d.text((48,y),ln,font=font(FR,42),fill=(226,233,255)); y+=58
photo_circle(img,W//2,975,140)
name="Ram Narayanan – Transformation Leader"
tw=d.textlength(name,font=font(FB,36)); d.text(((W-tw)/2,1150),name,font=font(FB,36),fill=WHITE)
sub="Architect of CHANGEReadyX™"
tw=d.textlength(sub,font=font(FR,30)); d.text(((W-tw)/2,1202),sub,font=font(FR,30),fill=BRONZE)
footer(img,1)
slides.append(img)
# 2..7 content
slides.append(content_slide(2,"TODAY IT'S PUBLIC","TAPAS Growth Autopilot","The local-first system that runs TAPAS Advisory's presence across eight platforms — now open on GitHub for any practitioner to study.","8 platforms · 1 local backend"))
slides.append(content_slide(3,"WHAT IT DOES · 01","One connection centre","LinkedIn · YouTube · Instagram\nX · Spotify · Bluesky\nMastodon · SoundCloud\n\nOAuth 2.0 behind a single local backend, with tokens encrypted at rest."))
slides.append(content_slide(4,"WHAT IT DOES · 02","Golden Hour planning","30 / 60 / 90-minute campaign plans built from connected accounts and due tasks.\n\nThe daily hour of engagement — planned, not improvised."))
slides.append(content_slide(5,"WHAT IT DOES · 03","AI drafts. Humans decide.","Gemini drafts the comments. A human reviews every single one. Nothing posts itself.\n\nAutomation proposes. Judgment disposes."))
slides.append(content_slide(6,"WHAT IT DOES · 04","Numbers with provenance","Community intelligence and analytics snapshots where every figure traces back to the provider response that produced it.\n\nDemo data is labelled demo. Always."))
slides.append(content_slide(7,"THE PRINCIPLE","Why local-first?","Tokens stay on my machine, encrypted at rest. No third-party SaaS ever holds the accounts.\n\nThe same people-first principle behind CHANGEReadyX™ — applied to my own marketing."))
# 8 CLOSING
img=gradient(); logo_chip(img); watermark(img); d=ImageDraw.Draw(img)
d.text((48,268),"BUILD YOUR OWN ENGINE",font=font(FB,30),fill=BRONZE)
y=330
for ln in wrap(d,"Study the code.",font(FB,80),W-96):
    d.text((48,y),ln,font=font(FB,80),fill=WHITE); y+=100
y+=8
repo="github.com/tapasadvisory/\ntapas-growth-autopilot"
for ln in repo.split("\n"):
    d.text((48,y),ln,font=font(FB,40),fill=CYAN); y+=54
photo_circle(img,W//2,915,130)
name="Ram Narayanan – Transformation Leader"
tw=d.textlength(name,font=font(FB,36)); d.text(((W-tw)/2,1086),name,font=font(FB,36),fill=WHITE)
sub="Architect of CHANGEReadyX™, TAPAS Advisory"
tw=d.textlength(sub,font=font(FR,30)); d.text(((W-tw)/2,1138),sub,font=font(FR,30),fill=BRONZE)
diag="Where does your transformation stand?  tapasadvisory.com/diagnostic"
tw=d.textlength(diag,font=font(FS,27)); d.text(((W-tw)/2,1210),diag,font=font(FS,27),fill=(226,233,255))
footer(img,8)
slides.append(img)

for i,s in enumerate(slides,1):
    s.save(f"{OUT}/slide-{i}.png")
pdf=f"{OUT}/tapas-growth-autopilot-carousel.pdf"
slides[0].save(pdf,save_all=True,append_images=slides[1:],resolution=144.0)
print("built", len(slides), "slides ->", pdf)
