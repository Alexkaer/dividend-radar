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
if (require.main === module) {
  const input = path.resolve(process.argv[2]), root = path.resolve(__dirname, '..');
  if (input === root || input.startsWith(root + path.sep)) throw new Error('Plaintext must remain outside public repository');
  const report = JSON.parse(fs.readFileSync(input,'utf8'));
  const output = process.argv[3] || 'data/strategies.enc.json';
  fs.writeFileSync(output, JSON.stringify(encrypt(report, process.env.STRATEGY_LOGIN_USERNAME, process.env.STRATEGY_LOGIN_PASSWORD)) + '\n');
  console.log('Encrypted strategy snapshot ready.');
}
module.exports={encrypt};
