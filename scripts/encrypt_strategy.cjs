const fs = require('node:fs');
const crypto = require('node:crypto');
const path = require('node:path');
function encrypt(report, username, password) {
  if (!username || !password) throw new Error('Missing private login credentials');
  const salt = crypto.randomBytes(32), iv = crypto.randomBytes(12), iterations = 600000;
  const key = crypto.pbkdf2Sync(username + '\0' + password, salt, iterations, 32, 'sha256');
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  cipher.setAAD(Buffer.from('dividend-strategy-v1'));
  const payload = Buffer.concat([cipher.update(JSON.stringify(report)), cipher.final(), cipher.getAuthTag()]);
  return {version:1, kdf:'PBKDF2-SHA256', iterations, salt:salt.toString('base64'), iv:iv.toString('base64'), ciphertext:payload.toString('base64')};
}
function decrypt(envelope,username,password){
  if(envelope.version!==1||envelope.iterations!==600000||envelope.kdf!=='PBKDF2-SHA256')throw new Error('Unsupported snapshot');
  const key=crypto.pbkdf2Sync(username+'\0'+password,Buffer.from(envelope.salt,'base64'),envelope.iterations,32,'sha256');
  const cipher=crypto.createDecipheriv('aes-256-gcm',key,Buffer.from(envelope.iv,'base64'));
  const payload=Buffer.from(envelope.ciphertext,'base64');cipher.setAAD(Buffer.from('dividend-strategy-v1'));cipher.setAuthTag(payload.subarray(-16));
  return JSON.parse(Buffer.concat([cipher.update(payload.subarray(0,-16)),cipher.final()]).toString('utf8'));
}
if (require.main === module) {
  if(process.argv[2]==='--decrypt'){
    const output=path.resolve(process.argv[4]),root=path.resolve(__dirname,'..');
    if(output===root||output.startsWith(root+path.sep))throw new Error('Plaintext must remain outside public repository');
    const envelope=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
    fs.writeFileSync(output,JSON.stringify(decrypt(envelope,process.env.STRATEGY_LOGIN_USERNAME,process.env.STRATEGY_LOGIN_PASSWORD)),{mode:0o600});
    console.log('Previous snapshot decrypted in private temporary directory.');
    return;
  }
  const input = path.resolve(process.argv[2]), root = path.resolve(__dirname, '..');
  if (input === root || input.startsWith(root + path.sep)) throw new Error('Plaintext must remain outside public repository');
  const report = JSON.parse(fs.readFileSync(input,'utf8'));
  const output = process.argv[3] || 'data/strategies.enc.json';
  fs.writeFileSync(output, JSON.stringify(encrypt(report, process.env.STRATEGY_LOGIN_USERNAME, process.env.STRATEGY_LOGIN_PASSWORD)) + '\n');
  console.log('Encrypted strategy snapshot ready.');
}
module.exports={encrypt,decrypt};
