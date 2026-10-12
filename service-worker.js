const CACHE="ops-hub-v1.5";
const RELEASE='1.5';
const ASSETS=['./','./index.html','./ops-saver.html','./manifest.webmanifest','./icon-192.png','./icon-512.png'];
const scope=new URL(self.registration.scope);
const assetURLs=new Set(ASSETS.map(p=>new URL(p,scope).href));
self.addEventListener('install',e=>{
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)).then(()=>self.skipWaiting()));
});
self.addEventListener('activate',e=>{
  e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('ops-hub-v')&&k!==CACHE).map(k=>caches.delete(k))))
    .then(()=>self.clients.claim()).then(()=>self.clients.matchAll({type:'window'})).then(clients=>clients.forEach(client=>client.postMessage({type:'OPS_HUB_VERSION',version:RELEASE}))));
});
self.addEventListener('message',e=>{if(e.data?.type==='GET_OPS_HUB_VERSION')e.source?.postMessage({type:'OPS_HUB_VERSION',version:RELEASE});});
self.addEventListener('fetch',e=>{
  const url=new URL(e.request.url);
  if(e.request.method!=='GET'||url.origin!==scope.origin||!url.pathname.startsWith(scope.pathname))return;
  const key=url.origin+url.pathname;
  if(e.request.mode!=='navigate'&&!assetURLs.has(key))return;
  e.respondWith((async()=>{
    const cache=await caches.open(CACHE);
    try{
      const response=await fetch(e.request,{cache:'no-store'});
      if(response.ok)await cache.put(e.request,response.clone());
      return response;
    }catch(error){
      const saved=await cache.match(e.request,{ignoreSearch:true});if(saved)return saved;
      if(e.request.mode==='navigate')return await cache.match(new URL('./index.html',scope).href)||new Response('Offline copy unavailable',{status:503});
      return new Response('Offline resource unavailable',{status:503});
    }
  })());
});
