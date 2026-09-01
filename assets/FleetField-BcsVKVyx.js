import{r as b,j as I}from"./index-BZA4sm63.js";import{W as q,S as G,P as N,B as L,a as H,C as W,b as O,A as V,L as Y,c as $,d as X}from"./three.module-CHevs6wk.js";function K({litFraction:w}){const C=b.useRef(null),y=b.useRef(w);return y.current=w,b.useEffect(()=>{const u=C.current;if(!u)return;let n;try{n=new q({antialias:!1,alpha:!0,powerPreference:"low-power"})}catch{return}n.setPixelRatio(Math.min(window.devicePixelRatio,1.75)),n.setClearColor(0,0),u.appendChild(n.domElement);const F=new G,r=new N(52,1,1,400);r.position.set(0,27,40),r.lookAt(0,0,-48);const v=3.1,i=92,d=78,o=i*d,p=new Float32Array(o*3),S=new Float32Array(o),E=new Float32Array(o),l=new Float32Array(o);for(let e=0;e<o;e++)l[e]=e/o;for(let e=o-1;e>0;e--){const t=Math.random()*(e+1)|0,s=l[e];l[e]=l[t],l[t]=s}for(let e=0;e<o;e++){const t=e%i,s=e/i|0;p[e*3]=(t-i/2)*v,p[e*3+1]=0,p[e*3+2]=-s*v+30,S[e]=l[e],E[e]=Math.random()}const T=new L(p,3),k=new L(S,1),z=new L(E,1),m=new H;m.setAttribute("position",T),m.setAttribute("aRank",k),m.setAttribute("aPhase",z);const g=[];for(let e=0;e<d;e++)for(let t=0;t<i;t++){const s=e*i+t;t+1<i&&g.push(s,s+1),e+1<d&&g.push(s,s+i)}const c=new H;c.setAttribute("position",T),c.setAttribute("aRank",k),c.setAttribute("aPhase",z),c.setIndex(g);const a={uTime:{value:0},uLit:{value:w},uScroll:{value:0},uCalm:{value:1},uDpr:{value:n.getPixelRatio()},uDim:{value:new W(7301336)},uAccent:{value:new W(4406271)}},P=new O({uniforms:a,transparent:!0,depthWrite:!1,blending:V,vertexShader:`
        uniform float uTime, uLit, uScroll, uDpr;
        attribute float aRank, aPhase;
        varying float vLit, vFade, vPulse;
        void main() {
          vec3 p = position;
          // Two slow, non-commensurate swells: the plane breathes rather than
          // ticking, so nothing on screen ever looks like a loading bar.
          p.y += sin(p.x * 0.055 + uTime * 0.21) * 2.6
               + cos(p.z * 0.041 - uTime * 0.16) * 3.4
               + sin((p.x + p.z) * 0.021 + uTime * 0.09) * 1.8;
          p.z += uScroll * 26.0;
          p.z = mod(p.z - 30.0, ${(d*v).toFixed(1)}) + 30.0 - ${(d*v).toFixed(1)};

          vLit = step(aRank, uLit);
          vPulse = 0.5 + 0.5 * sin(uTime * 0.7 + aPhase * 6.2831);

          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          float d = -mv.z;
          vFade = smoothstep(240.0, 55.0, d) * smoothstep(6.0, 22.0, d);
          gl_Position = projectionMatrix * mv;
          gl_PointSize = (2.1 + vPulse * 1.5) * uDpr * (66.0 / max(d, 1.0));
        }
      `,fragmentShader:`
        uniform vec3 uDim, uAccent;
        uniform float uCalm;
        varying float vLit, vFade, vPulse;
        void main() {
        #ifdef LATTICE
          // The grid: barely there, but it is what gives the plane its shape.
          gl_FragColor = vec4(uDim, vFade * 0.34 * uCalm);
        #else
          // Only the holdout is drawn as a node. Everything else is lattice.
          if (vLit < 0.5) discard;
          vec2 d = gl_PointCoord - 0.5;
          float r2 = dot(d, d);
          if (r2 > 0.25) discard;
          float a = smoothstep(0.25, 0.0, r2);
          gl_FragColor = vec4(uAccent, a * vFade * (0.62 + vPulse * 0.34) * uCalm);
        #endif
        }
      `}),f=P.clone();f.uniforms=a,f.defines={LATTICE:""};const _=new Y(c,f),B=new $(m,P);F.add(_,B);const R=new X;let x=0,A=!0;const h=()=>{const e=u.clientWidth||window.innerWidth,t=u.clientHeight||window.innerHeight;n.setSize(e,t,!1),r.aspect=e/t,r.updateProjectionMatrix(),a.uDpr.value=n.getPixelRatio()};h();const M=()=>{if(x=requestAnimationFrame(M),!A)return;a.uTime.value=R.getElapsedTime(),a.uLit.value=y.current;const e=document.documentElement.scrollHeight-window.innerHeight;a.uScroll.value=e>0?window.scrollY/e:0,a.uCalm.value=1-Math.min(window.scrollY/(window.innerHeight*1.15),1)*.72,r.position.y=27-a.uScroll.value*7,r.lookAt(0,0,-48),n.render(F,r)};x=requestAnimationFrame(M);const D=()=>{A=!document.hidden,A&&R.getDelta()};document.addEventListener("visibilitychange",D);const j=new ResizeObserver(h);return j.observe(u),window.addEventListener("resize",h),()=>{cancelAnimationFrame(x),document.removeEventListener("visibilitychange",D),window.removeEventListener("resize",h),j.disconnect(),m.dispose(),c.dispose(),P.dispose(),f.dispose(),n.dispose(),n.domElement.remove()}},[]),I.jsx("div",{className:"rl-field",ref:C,"aria-hidden":"true"})}export{K as default};
