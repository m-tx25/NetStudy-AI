# 传智杯 Web 项目

本目录为传智杯 Web 方向的开发项目。

## 环境说明（本机）

本机安装了 SteamTools（Watt Toolkit）加速器，它会在本机 443 端口做 TLS 中间人，
用自签发的 `SteamTools Certificate` 重新签发 github.com 等域名的证书。
因此 git 默认会报错：

- `schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS`
- 或 `SSL certificate OpenSSL verify result: unable to get local issuer certificate (20)`

本仓库已在 `.git/config` 中做好以下配置，使 git 能正常访问 GitHub：

- `http.sslBackend = openssl`
- `http.sslCAInfo = <本仓库>/.git-trust/ca-bundle-plus-steamtools.pem`

其中 `.git-trust/ca-bundle-plus-steamtools.pem` 是 git 自带的 CA 根证书包，
加上系统信任库中的 SteamTools 根证书合并而成。该文件属于本机环境适配文件，
已在 `.gitignore` 中忽略，不会提交到仓库。

> 换到其它机器或不再使用加速器时，可执行
> `git config --unset http.sslBackend` 与 `git config --unset http.sslCAInfo` 恢复默认。

## 使用

```bash
git remote add origin <仓库地址>
git push -u origin main
```
