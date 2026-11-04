const assert=require('node:assert/strict');
const crypto=require('node:crypto');
const {encrypt}=require('./encrypt_strategy.cjs');
(async()=>{
  const data={groups:{triple:[{name:'private fixture'}]},asOf:'2026-11-04'};
  const e=encrypt(data,'fixture-user','fixture-password');
  assert(!JSON.stringify(e).includes('private fixture'));
  async function decrypt(user,password,envelope=e){
    const material=await crypto.webcrypto.subtle.importKey('raw',new TextEncoder().encode(user+'\0'+password),'PBKDF2',false,['deriveBits']);
    const bits=await crypto.webcrypto.subtle.deriveBits({name:'PBKDF2',salt:Buffer.from(envelope.salt,'base64'),iterations:envelope.iterations,hash:'SHA-256'},material,256);
    const key=await crypto.webcrypto.subtle.importKey('raw',bits,'AES-GCM',false,['decrypt']);
    const plain=await crypto.webcrypto.subtle.decrypt({name:'AES-GCM',iv:Buffer.from(envelope.iv,'base64'),additionalData:Buffer.from('dividend-strategy-v1'),tagLength:128},key,Buffer.from(envelope.ciphertext,'base64'));
    assert.equal(key.extractable,false);
    return JSON.parse(Buffer.from(plain).toString());
  }
  assert.deepEqual(await decrypt('fixture-user','fixture-password'),data);
  await assert.rejects(decrypt('other-user','fixture-password'));
  await assert.rejects(decrypt('fixture-user','wrong-password'));
  const damaged={...e,ciphertext:Buffer.from('tampered').toString('base64')};
  await assert.rejects(decrypt('fixture-user','fixture-password',damaged));
  const next=encrypt(data,'fixture-user','fixture-password');
  assert.notEqual(next.salt,e.salt);assert.notEqual(next.iv,e.iv);
  assert.deepEqual(await decrypt('fixture-user','fixture-password',next),data);
  console.log('Strategy encryption and browser decryption checks passed.');
})().catch(()=>{console.error('Strategy encryption check failed');process.exitCode=1;});
