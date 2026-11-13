try {
(function(){
'use strict';
// Seamless loop: duplicate the track content once so translateX(-50%) wraps perfectly.
document.querySelectorAll('.anim-marquee-track').forEach(function(track){
  if(track.getAttribute('data-dup')) return;
  track.setAttribute('data-dup','1');
  track.innerHTML += track.innerHTML;
});
}());
} catch (e) { /* isolated animation feature */ }
try {
(function(){
'use strict';
var REDUCE = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
function countUp(el){
  var target = parseFloat(el.getAttribute('data-count') || '0');
  var decimals = parseInt(el.getAttribute('data-decimals') || '0', 10);
  var prefix = el.getAttribute('data-prefix') || '';
  var suffix = el.getAttribute('data-suffix') || '';
  if(REDUCE){ el.textContent = prefix + target.toFixed(decimals) + suffix; el.classList.add('done'); return; }
  var dur = parseFloat(el.getAttribute('data-duration') || '1.6');
  var t0 = null;
  function step(ts){
    if(t0 === null) t0 = ts;
    var p = Math.min(1, (ts - t0) / (dur * 1000));
    var eased = 1 - Math.pow(1 - p, 3);
    el.textContent = prefix + (target * eased).toFixed(decimals) + suffix;
    if(p < 1){ requestAnimationFrame(step); }
    else { el.textContent = prefix + target.toFixed(decimals) + suffix; el.classList.add('done'); }
  }
  requestAnimationFrame(step);
}
var io = new IntersectionObserver(function(entries){
  entries.forEach(function(e){
    if(e.isIntersecting){ countUp(e.target); io.unobserve(e.target); }
  });
}, {threshold: 0.4});
document.querySelectorAll('.anim-count[data-count]').forEach(function(el){ io.observe(el); });
}());
} catch (e) { /* isolated animation feature */ }
try {
(function(){
'use strict';
var REDUCE = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
var els = document.querySelectorAll('.anim-clip,.anim-mask,.anim-reveal-up');
if(REDUCE){ els.forEach(function(el){ el.classList.add('inview'); }); return; }
var io = new IntersectionObserver(function(entries){
  entries.forEach(function(e){
    if(e.isIntersecting){
      var el = e.target;
      var delay = el.getAttribute('data-delay') || '0';
      el.style.transitionDelay = delay + 'ms';
      el.classList.add('inview');
      io.unobserve(el);
    }
  });
}, {threshold: 0.2, rootMargin: '0px 0px -8% 0px'});
els.forEach(function(el){ io.observe(el); });
}());
} catch (e) { /* isolated animation feature */ }
try {
(function(){
'use strict';
var REDUCE = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
var FINE = window.matchMedia('(hover:hover) and (pointer:fine)').matches;
if(REDUCE || !FINE) return;
var cursor = document.querySelector('.anim-cursor');
if(!cursor){
  cursor = document.createElement('div');
  cursor.className = 'anim-cursor';
  cursor.innerHTML = '<span class="anim-cursor-label"><span class="anim-cursor-label-track"></span></span>';
  document.body.appendChild(cursor);
}
var track = cursor.querySelector('.anim-cursor-label-track');
var tx = 0, ty = 0, x = 0, y = 0;
window.addEventListener('mousemove', function(e){ tx = e.clientX; ty = e.clientY; });
(function loop(){
  x += (tx - x) * 0.18; y += (ty - y) * 0.18;
  cursor.style.transform = 'translate(' + x + 'px,' + y + 'px) translate(-50%,-50%)';
  requestAnimationFrame(loop);
})();
document.querySelectorAll('[data-cursor]').forEach(function(el){
  el.addEventListener('mouseenter', function(){
    var label = el.getAttribute('data-cursor') || 'View';
    track.textContent = (label + ' \u2022 ').repeat(4);
    track.innerHTML += track.innerHTML;
    cursor.classList.add('is-label');
  });
  el.addEventListener('mouseleave', function(){ cursor.classList.remove('is-label'); });
});
}());
} catch (e) { /* isolated animation feature */ }
try {
(function(){
'use strict';
var REDUCE = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
var bars = document.querySelectorAll('.anim-blur-bar');
if(!bars.length || REDUCE) return;
var maxBlur = 14, ticking = false;
function update(){
  ticking = false;
  var h = document.documentElement.scrollHeight - window.innerHeight;
  var p = h > 0 ? Math.min(1, window.scrollY / h) : 0;
  var blur = Math.round(maxBlur * Math.min(1, p * 4));
  bars.forEach(function(b){
    b.style.backdropFilter = 'blur(' + blur + 'px)';
    b.style.webkitBackdropFilter = 'blur(' + blur + 'px)';
  });
}
window.addEventListener('scroll', function(){
  if(!ticking){ ticking = true; requestAnimationFrame(update); }
}, {passive:true});
update();
}());
} catch (e) { /* isolated animation feature */ }
try {
(function(){
'use strict';
var REDUCE = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
var groups = document.querySelectorAll('[data-reveal-group],[data-reveal-group-nested]');
if(REDUCE){ groups.forEach(function(g){ g.classList.add('inview'); }); return; }
groups.forEach(function(g){
  Array.prototype.forEach.call(g.children, function(child, i){
    child.style.setProperty('--i', String(i));
  });
});
var io = new IntersectionObserver(function(entries){
  entries.forEach(function(e){
    if(e.isIntersecting){ e.target.classList.add('inview'); io.unobserve(e.target); }
  });
}, {threshold: 0.15, rootMargin: '0px 0px -6% 0px'});
groups.forEach(function(g){ io.observe(g); });
}());
} catch (e) { /* isolated animation feature */ }
try {
(function(){
'use strict';
var REDUCE = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
var hasGsap = typeof gsap !== 'undefined' && typeof ScrollTrigger !== 'undefined';
document.querySelectorAll('[data-split-init],[data-scrub-init]').forEach(function(el){
  if(!el.querySelector('.split-char') && !el.querySelector('.split-word')){
    var useWords = el.hasAttribute('data-split-words');
    var text = el.textContent || '';
    el.textContent = '';
    var parts = useWords ? text.split(/(\s+)/) : text.split('');
    parts.forEach(function(part){
      if(!part) return;
      var span = document.createElement('span');
      span.className = useWords ? 'split-word' : 'split-char';
      span.textContent = part.trim() === '' ? '\u00A0' : part;
      if(useWords){ el.appendChild(span); el.appendChild(document.createTextNode(' ')); }
      else { var mask = document.createElement('span'); mask.className = 'split-mask'; mask.appendChild(span); el.appendChild(mask); }
    });
  }
  var chars = el.querySelectorAll('.split-char,.split-word');
  if(REDUCE || !hasGsap || !chars.length){ chars.forEach(function(c){ c.style.transform='none'; c.style.opacity='1'; }); return; }
  gsap.registerPlugin(ScrollTrigger);
  gsap.fromTo(chars,
    {yPercent: 110, opacity: 0},
    {yPercent: 0, opacity: 1, ease: 'power3.out', stagger: 0.02,
     scrollTrigger: {trigger: el, start: 'top 85%', end: 'bottom 45%', scrub: 0.6}}
  );
});
}());
} catch (e) { /* isolated animation feature */ }
try {
(function(){
'use strict';
var REDUCE = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
var els = document.querySelectorAll('[data-text-fade-in]');
if(REDUCE){ els.forEach(function(el){ el.classList.add('inview'); }); return; }
els.forEach(function(el){
  var lines = el.querySelectorAll('.anim-line');
  if(lines.length){ lines.forEach(function(l,i){ l.style.setProperty('--i', String(i)); }); }
  else el.style.setProperty('--i','0');
});
var io = new IntersectionObserver(function(entries){
  entries.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add('inview'); io.unobserve(e.target); } });
}, {threshold: 0.25});
els.forEach(function(el){ io.observe(el); });
}());
} catch (e) { /* isolated animation feature */ }
try {
(function(){
'use strict';
var REDUCE = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
document.querySelectorAll('[data-wipe]').forEach(function(el){
  if(el.querySelector('.anim-wipe')) return;
  var text = el.textContent || '';
  el.textContent = '';
  text.split(/(\s+)/).forEach(function(part, i){
    if(!part) return;
    var wrap = document.createElement('span');
    wrap.className = 'anim-wipe' + (el.hasAttribute('data-wipe-left') ? ' anim-wipe-l' : '');
    var inner = document.createElement('span');
    inner.textContent = part.trim() === '' ? '\u00A0' : part;
    wrap.style.setProperty('--i', String(i));
    wrap.appendChild(inner);
    el.appendChild(wrap);
    if(part.match(/\s/)) el.appendChild(document.createTextNode(' '));
  });
});
var els = document.querySelectorAll('[data-wipe]');
if(REDUCE){ els.forEach(function(el){ el.classList.add('inview'); }); return; }
var io = new IntersectionObserver(function(entries){
  entries.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add('inview'); io.unobserve(e.target); } });
}, {threshold: 0.3});
els.forEach(function(el){ io.observe(el); });
}());
} catch (e) { /* isolated animation feature */ }
try {
(function(){
'use strict';
var REDUCE = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
document.querySelectorAll('[data-scroll-read]').forEach(function(el){
  if(el.querySelector('.sr-word')) return;
  var text = el.textContent || '';
  el.textContent = '';
  var words = text.split(/(\s+)/).filter(Boolean);
  words.forEach(function(w){
    var s = document.createElement('span');
    s.className = 'sr-word';
    s.textContent = w.trim() === '' ? '\u00A0' : w;
    el.appendChild(s);
    if(w.match(/\s/)) el.appendChild(document.createTextNode(' '));
  });
  var spans = el.querySelectorAll('.sr-word');
  if(REDUCE){ spans.forEach(function(s){ s.classList.add('read'); }); return; }
  function update(){
    var r = el.getBoundingClientRect(), vh = window.innerHeight;
    // read progress: how far the block has travelled past the 75% viewport line
    var p = Math.max(0, Math.min(1, (vh * 0.75 - r.top) / (r.height + vh * 0.25)));
    var n = Math.floor(p * spans.length);
    spans.forEach(function(s, i){ s.classList.toggle('read', i < n); });
  }
  window.addEventListener('scroll', function(){ requestAnimationFrame(update); }, {passive:true});
  update();
});
}());
} catch (e) { /* isolated animation feature */ }
try {
(function(){
'use strict';
var REDUCE = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
var FINE = window.matchMedia('(hover:hover) and (pointer:fine)').matches;
if(REDUCE || !FINE) return;
document.querySelectorAll('.anim-tilt-scene').forEach(function(scene){
  scene.querySelectorAll('.anim-tilt').forEach(function(card){
    var max = parseFloat(card.getAttribute('data-tilt-max') || '10');
    scene.addEventListener('pointermove', function(e){
      var r = card.getBoundingClientRect();
      var px = (e.clientX - r.left) / r.width - 0.5;
      var py = (e.clientY - r.top) / r.height - 0.5;
      card.style.transform = 'rotateY(' + (px * max * 2) + 'deg) rotateX(' + (-py * max * 2) + 'deg)';
    });
    scene.addEventListener('pointerleave', function(){ card.style.transform = 'rotateY(0) rotateX(0)'; });
  });
});
}());
} catch (e) { /* isolated animation feature */ }
try {
(function(){
'use strict';
gsap.registerPlugin(ScrollTrigger);
if(window.matchMedia('(prefers-reduced-motion:reduce)').matches) return;

// ── Hero Timeline ──
var tl = gsap.timeline({defaults:{ease:'power3.out'}});
tl.from('.gsap-hero-badge', {y:20,opacity:0,duration:0.5})
  .from('.gsap-hero-title', {y:30,opacity:0,duration:0.7},'-=0.3')
  .from('.gsap-hero-sub',   {y:20,opacity:0,duration:0.6},'-=0.3')
  .from('.gsap-hero-cta',   {y:20,opacity:0,duration:0.5},'-=0.2');

// ── Staggered Items ──
gsap.utils.toArray('.gsap-stagger-item').forEach(function(el,i){
  gsap.from(el,{
    scrollTrigger:{trigger:el,start:'top 85%'},
    y:30,opacity:0,duration:0.6,delay:i*0.08,ease:'power2.out'
  });
});

// ── Scroll Reveals ──
gsap.utils.toArray('.gsap-reveal').forEach(function(el){
  gsap.from(el,{
    scrollTrigger:{trigger:el,start:'top 85%'},
    y:40,opacity:0,duration:0.8,ease:'power2.out'
  });
});

// ── Scale Reveal ──
gsap.utils.toArray('.gsap-scale').forEach(function(el){
  gsap.from(el,{
    scrollTrigger:{trigger:el,start:'top 85%'},
    scale:0.8,opacity:0,duration:0.8,ease:'back.out(1.4)'
  });
});

// ── GSAP Count-Up ──
gsap.utils.toArray('.gsap-count').forEach(function(el){
  var t=parseInt(el.getAttribute('data-target')||el.textContent.replace(/[^0-9]/g,''),10)||0;
  var o={val:0};
  gsap.to(o,{
    val:t,duration:2,ease:'power2.out',
    scrollTrigger:{trigger:el,start:'top 85%'},
    onUpdate:function(){el.textContent=Math.round(o.val).toLocaleString();}
  });
});

// ── GSAP Parallax ──
gsap.utils.toArray('.gsap-parallax').forEach(function(el){
  var d=parseFloat(el.getAttribute('data-depth'))||0.3;
  gsap.to(el,{
    y:function(){return (1-d)*100*0.3;},
    ease:'none',
    scrollTrigger:{trigger:el.parentElement,start:'top bottom',end:'bottom top',scrub:true}
  });
});

// ── GSAP Pinned Sections ──
gsap.utils.toArray('[data-pin]').forEach(function(el){
  ScrollTrigger.create({
    trigger:el,start:'top top',end:'bottom top',pin:true,
    pinSpacing:false,markers:false
  });
});

// ── GSAP Horizontal Scroll ──
gsap.utils.toArray('[data-horizontal-scroll]').forEach(function(el){
  var wrap=el.querySelector('[data-horizontal-wrap]');
  if(!wrap) return;
  var w=wrap.scrollWidth-window.innerWidth;
  if(w<=0) return;
  gsap.to(wrap,{
    x:function(){return -w;},
    ease:'none',
    scrollTrigger:{trigger:el,start:'top top',end:function(){return '+='+w;},pin:true,scrub:1,anticipatePin:1}
  });
});
}());
} catch (e) { /* isolated animation feature */ }
try {
(function(){
'use strict';
if(window.matchMedia('(prefers-reduced-motion:reduce)').matches) return;

// ── Header Shrink on Scroll ──
var header = document.querySelector('.anim-header-short');
if(header) {
  ScrollTrigger.create({
    trigger:document.body,start:'top -48px',
    onToggle:function(self){header.classList.toggle('scrolled',self.isActive);}
  });
}

// ── GSAP Header Reveal ──
var hdr = document.querySelector('.gsap-header-reveal');
if(hdr) {
  gsap.from(hdr, {y:-80,opacity:0,duration:0.8,ease:'power3.out'});
}

// ── FAQ Accordion ──
document.querySelectorAll('.gsap-accordion-item').forEach(function(el){
  var body = el.querySelector('.accordion-body');
  var h = body ? body.scrollHeight : 0;
  var summary = el.querySelector('.accordion-summary');
  if(summary) {
    summary.addEventListener('click',function(e){
      e.preventDefault();
      if(el.classList.contains('open')) {
        gsap.to(body, {height:0,duration:0.3,ease:'power2.in',onComplete:function(){el.classList.remove('open');}});
      } else {
        el.classList.add('open');
        gsap.fromTo(body, {height:0}, {height:h,duration:0.4,ease:'power2.out'});
      }
    });
  }
});

// ── Testimonial GSAP Carousel ──
(function(){
var carousel = document.querySelector('.gsap-carousel');
if(!carousel) return;
var track = carousel.querySelector('.carousel-track');
var slides = carousel.querySelectorAll('.carousel-slide');
var dots = carousel.querySelectorAll('.carousel-dot');
if(!slides.length) return;
var current = 0;
function goTo(idx){
  if(idx<0) idx=slides.length-1;
  if(idx>=slides.length) idx=0;
  current=idx;
  gsap.to(track, {x:function(){return -idx*100+'%';},duration:0.6,ease:'power2.out'});
  slides.forEach(function(s,i){s.classList.toggle('active',i===idx);});
  dots.forEach(function(d,i){d.classList.toggle('active',i===idx);});
}
dots.forEach(function(d,i){
  d.addEventListener('click',function(){goTo(i);});
});
if(slides.length>1){
  setInterval(function(){goTo(current+1);},4000);
}
}());

// ── How It Works Line Draw ──
gsap.utils.toArray('.gsap-line-draw').forEach(function(el){
  el.querySelectorAll('.step-line').forEach(function(line){
    gsap.from(line, {
      scaleX:0,scaleY:0,duration:0.8,ease:'power2.out',
      scrollTrigger:{trigger:line.parentElement,start:'top 80%'}
    });
  });
  el.querySelectorAll('.gsap-stagger-item').forEach(function(item,i){
    gsap.from(item, {
      scrollTrigger:{trigger:item,start:'top 85%'},
      y:30,opacity:0,duration:0.6,delay:i*0.08,ease:'power2.out'
    });
  });
});

// ── Comparison Highlight ──
gsap.utils.toArray('.anim-compare-highlight').forEach(function(el){
  ScrollTrigger.create({
    trigger:el,start:'top 85%',
    onEnter:function(){el.classList.add('anim-visible');}
  });
});

// ── Feature Grid GSAP Stagger ──
gsap.utils.toArray('.gsap-feature-stagger').forEach(function(el){
  gsap.from(el.children, {
    scrollTrigger:{trigger:el,start:'top 85%'},
    y:40,opacity:0,duration:0.6,stagger:0.08,ease:'power2.out'
  });
});

// ── CTA Gradient Shift ──
gsap.utils.toArray('.anim-gradient-shift').forEach(function(el){
  gsap.to(el, {
    backgroundPosition:'100% 50%',
    ease:'none',
    scrollTrigger:{trigger:el,start:'top bottom',end:'bottom top',scrub:1}
  });
});
}());
} catch (e) { /* isolated animation feature */ }
try {
(function(){
'use strict';
var SD = 0.08;
var TH = 0.15;
var REDUCE = window.matchMedia('(prefers-reduced-motion:reduce)').matches;

// ── Scroll Progress Bar ──
(function(){
var pb = document.querySelector('.anim-scroll-progress');
if(pb && !REDUCE) {
  var ticking = false;
  window.addEventListener('scroll',function(){
    if(!ticking) { requestAnimationFrame(function(){
      var h = document.documentElement.scrollHeight - window.innerHeight;
      pb.style.transform = 'scaleX(' + Math.min(window.scrollY / Math.max(h,1), 1) + ')';
      ticking = false;
    }); ticking = true; }
  },{passive:true});
}
})();

// ── IntersectionObserver for Reveals ──
(function(){
var obs = new IntersectionObserver(function(entries){
  entries.forEach(function(entry){
    if(!entry.isIntersecting) return;
    var el = entry.target;
    var anim = el.getAttribute('data-anim');
    if(anim === 'stagger') {
      var kids = el.children;
      for(var i=0;i<kids.length;i++) { (function(idx){
        setTimeout(function(){ kids[idx].classList.add('anim-visible'); }, idx * SD);
      })(i); }
    } else if(anim === 'grid-reveal') {
      el.classList.add('anim-visible');
      var kids = el.children;
      for(var i=0;i<kids.length;i++) { (function(idx){
        setTimeout(function(){ kids[idx].style.transitionDelay = (idx * SD)+'s'; kids[idx].classList.add('anim-visible'); }, 50);
      })(i); }
    }
    el.classList.add('anim-visible');
    if(anim !== 'keep') obs.unobserve(el);
  });
},{threshold:TH});

// Stagger parents
document.querySelectorAll('[data-anim="stagger"]').forEach(function(p){
  Array.from(p.children).forEach(function(c){ c.classList.add('anim-stagger-child'); obs.observe(c); });
});

// Grid reveals
document.querySelectorAll('[data-anim="grid-reveal"]').forEach(function(g){ obs.observe(g); });

// Direct anim elements
document.querySelectorAll('[data-anim]:not([data-anim="stagger"]):not([data-anim="grid-reveal"])').forEach(function(el){
  obs.observe(el);
});

// Stats
document.querySelectorAll('.anim-stat').forEach(function(el){ obs.observe(el); });
document.querySelectorAll('.anim-reveal-image').forEach(function(el){ obs.observe(el); });
})();

// ── Counter-Up ──
(function(){
if(REDUCE) return;
var co = new IntersectionObserver(function(entries){
  entries.forEach(function(entry){
    if(!entry.isIntersecting) return;
    var el = entry.target;
    var t = parseInt(el.getAttribute('data-target')||el.textContent.replace(/[^0-9]/g,''),10);
    if(!t) { co.unobserve(el); return; }
    var c = 0, st = Math.ceil(t / (1500/16));
    var tm = setInterval(function(){
      c += st; if(c>=t) { c=t; clearInterval(tm); }
      el.textContent = c.toLocaleString();
    },16);
    co.unobserve(el);
  });
},{threshold:0.3});
document.querySelectorAll('.anim-count-up,.anim-stat-value').forEach(function(el){ co.observe(el); });
})();
}());
} catch (e) { /* isolated animation feature */ }
try {
(function(){
'use strict';
var REDUCE = window.matchMedia('(prefers-reduced-motion:reduce)').matches;

// ── Custom Cursor ──
(function(){
var dot = document.querySelector('.cursor-dot');
var ring = document.querySelector('.cursor-ring');
if(!dot||!ring||REDUCE) return;
document.body.classList.add('cursor-custom');
var mx=0,my=0,rmx=0,rmy=0;
document.addEventListener('mousemove',function(e){mx=e.clientX;my=e.clientY;});
function frame(){
  dot.style.left=mx+'px';dot.style.top=my+'px';
  rmx+=(mx-rmx)*0.15;rmy+=(my-rmy)*0.15;
  ring.style.left=rmx+'px';ring.style.top=rmy+'px';
  requestAnimationFrame(frame);
}
frame();
document.querySelectorAll('a,button,[data-cursor="hover"]').forEach(function(el){
  el.addEventListener('mouseenter',function(){ring.classList.add('hovering');});
  el.addEventListener('mouseleave',function(){ring.classList.remove('hovering');});
  el.addEventListener('mousedown',function(){ring.classList.add('clicking');});
  el.addEventListener('mouseup',function(){ring.classList.remove('clicking');});
});
})();

// ── Magnetic Buttons ──
(function(){
document.querySelectorAll('.anim-magnetic').forEach(function(el){
  el.addEventListener('mousemove',function(e){
    var r=el.getBoundingClientRect();
    var dx=e.clientX-r.left-r.width/2;
    var dy=e.clientY-r.top-r.height/2;
    el.style.transform='translate('+(dx*0.3)+'px,'+(dy*0.3)+'px)';
  });
  el.addEventListener('mouseleave',function(){el.style.transform='';});
});
})();

// ── 3D Tilt Cards ──
(function(){
document.querySelectorAll('.anim-3d-tilt').forEach(function(el){
  el.addEventListener('mousemove',function(e){
    var r=el.getBoundingClientRect();
    var x=e.clientX-r.left,y=e.clientY-r.top;
    var rotX=((y/r.height)*-30+15).toFixed(1);
    var rotY=((x/r.width)*30-15).toFixed(1);
    el.style.setProperty('--rotX',rotX+'deg');
    el.style.setProperty('--rotY',rotY+'deg');
  });
  el.addEventListener('mouseleave',function(){
    el.style.setProperty('--rotX','0deg');
    el.style.setProperty('--rotY','0deg');
  });
});
})();

// ── Ripple Effect ──
(function(){
document.querySelectorAll('.anim-ripple').forEach(function(el){
  el.addEventListener('click',function(e){
    var r=el.getBoundingClientRect();
    var ri=document.createElement('span');
    ri.className='anim-ripple-effect';
    var size=Math.max(r.width,r.height);
    ri.style.width=ri.style.height=size+'px';
    ri.style.left=(e.clientX-r.left-size/2)+'px';
    ri.style.top=(e.clientY-r.top-size/2)+'px';
    el.appendChild(ri);
    setTimeout(function(){ri.remove();},600);
  });
});
})();

// ── Spotlight Follow ──
(function(){
var sp=document.querySelector('.anim-spotlight');
if(sp){
  sp.addEventListener('mousemove',function(e){
    var r=sp.getBoundingClientRect();
    sp.style.setProperty('--mx',((e.clientX-r.left)/r.width*100)+'%');
    sp.style.setProperty('--my',((e.clientY-r.top)/r.height*100)+'%');
  });
}
})();

// ── Particle System ──
(function(){
document.querySelectorAll('[data-particles]').forEach(function(container){
  var count=parseInt(container.getAttribute('data-particles'))||30;
  for(var i=0;i<count;i++){
    var p=document.createElement('div');
    if(Math.random()>0.7){
      p.className='anim-particle-diamond';
    } else {
      p.className='anim-particle-dot';
      var colors=['#6366f1','#a855f7','#ec4899','#22c55e','#f59e0b'];
      p.style.background=colors[Math.floor(Math.random()*colors.length)];
    }
    p.style.left=Math.random()*100+'%';
    p.style.top=(50+Math.random()*50)+'%';
    p.style.animationDelay=Math.random()*12+'s';
    p.style.animationDuration=(10+Math.random()*10)+'s';
    p.style.opacity=0.1+Math.random()*0.3;
    p.style.width=p.style.height=(3+Math.random()*4)+'px';
    container.appendChild(p);
  }
});
})();

// ── Parallax Depth on Mouse ──
(function(){
document.querySelectorAll('.anim-parallax').forEach(function(el){
  el.addEventListener('mousemove',function(e){
    var r=el.getBoundingClientRect();
    var x=(e.clientX-r.left)/r.width-0.5;
    var y=(e.clientY-r.top)/r.height-0.5;
    el.querySelectorAll('.anim-parallax-layer,.anim-parallax-depth').forEach(function(layer){
      var d=parseFloat(layer.getAttribute('data-depth'))||0.3;
      layer.style.transform='translate('+(-x*d*40)+'px,'+(-y*d*40)+'px)';
    });
  });
  el.addEventListener('mouseleave',function(){
    el.querySelectorAll('.anim-parallax-layer,.anim-parallax-depth').forEach(function(layer){
      layer.style.transform='';
    });
  });
});
})();

// ── Smooth Anchor Scrolling ──
(function(){
document.querySelectorAll('a[href^="#"]').forEach(function(a){
  a.addEventListener('click',function(e){
    var id=this.getAttribute('href');
    if(id==='#') return;
    var target=document.querySelector(id);
    if(target){e.preventDefault();target.scrollIntoView({behavior:'smooth',block:'start'});}
  });
});
})();
}());
} catch (e) { /* isolated animation feature */ }
try {
(function(){
'use strict';
var REDUCE = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
if(REDUCE || typeof gsap === 'undefined' || typeof ScrollTrigger === 'undefined') return;
gsap.registerPlugin(ScrollTrigger);

document.querySelectorAll('.anim-story').forEach(function(story){
  var steps = story.querySelectorAll('.anim-story-step');
  var progressContainer = story.querySelector('.anim-story-progress');
  var counterEl = story.querySelector('.anim-story-counter');
  var lines = progressContainer ? progressContainer.querySelectorAll('.anim-story-progress-line') : [];
  if(steps.length < 2) return;

  steps.forEach(function(step, i){
    var content = step.querySelector('.anim-story-step-content');
    ScrollTrigger.create({
      trigger: step,
      start: 'top 60%',
      end: 'bottom 40%',
      onEnter: function(){
        if(content) content.classList.add('active');
        lines.forEach(function(l, j){ l.classList.toggle('filled', j <= i); });
        if(counterEl) counterEl.textContent = String(i + 1).padStart(2, '0') + ' / ' + String(steps.length).padStart(2, '0');
      },
      onLeaveBack: function(){
        if(content) content.classList.remove('active');
        lines.forEach(function(l, j){ l.classList.toggle('filled', j < i); });
        if(counterEl && i > 0) counterEl.textContent = String(i).padStart(2, '0') + ' / ' + String(steps.length).padStart(2, '0');
      }
    });
  });

  // Show/hide progress indicator
  ScrollTrigger.create({
    trigger: story,
    start: 'top 80%',
    end: 'bottom 20%',
    onToggle: function(self){
      if(progressContainer) progressContainer.classList.toggle('visible', self.isActive);
      if(counterEl) counterEl.classList.toggle('visible', self.isActive);
    }
  });
});
}());
} catch (e) { /* isolated animation feature */ }
try {
(function(){
'use strict';
var REDUCE = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
if(REDUCE) return;
// Skip if CSS scroll-driven animations are supported (ring is CSS-only)
if(CSS && CSS.supports && CSS.supports('animation-timeline:scroll()')) return;

var ring = document.querySelector('.anim-progress-ring');
if(!ring) return;
var fill = ring.querySelector('.ring-fill');
var text = ring.querySelector('.ring-center');
var circumference = 2 * Math.PI * 20; // r=20
if(fill) fill.style.strokeDasharray = circumference;

function update(){
  var h = document.documentElement.scrollHeight - window.innerHeight;
  var p = h > 0 ? Math.min(window.scrollY / h, 1) : 0;
  if(fill) fill.style.strokeDashoffset = circumference * (1 - p);
  if(text) text.textContent = Math.round(p * 100);
  ring.classList.toggle('visible', p > 0.01 && p < 0.99);
}
update();
window.addEventListener('scroll', update, {passive:true});
window.addEventListener('resize', update, {passive:true});
}());
} catch (e) { /* isolated animation feature */ }