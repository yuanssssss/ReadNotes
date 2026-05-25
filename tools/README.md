# ReadNotes 加密工具使用教程

这个工具可以自动加密和解密 ReadNotes 中的敏感内容，使用 RSA + AES-256-GCM 加密算法，基于 OpenSSL CMS 标准。

## 前置要求

- Python 3.10+
- OpenSSL 命令行工具（通常系统自带）

检查 OpenSSL 是否可用：
```bash
openssl version
```

## 快速开始

### 1. 初始化密钥（首次使用）

```bash
cd d:/Document/ReadNotes
python tools/secure_text.py init
```

这会在 `keys/` 目录下生成三个文件：
- `private_key.pem` - 私钥（**务必保密**，用于解密）
- `public_key.pem` - 公钥
- `public_cert.pem` - 公钥证书（用于加密）

⚠️ **重要**：`private_key.pem` 是解密的唯一凭证，丢失后无法恢复加密内容。建议备份到安全位置。

### 2. 标记需要加密的内容

在 Markdown 文件中，用 `/** Encrypt` 和 `**/` 包裹需要加密的文本：

```markdown
# 我的笔记

这是公开内容。

/** Encrypt
这是需要加密的敏感内容。
可以是多行文本。
包含任何你不想公开的信息。
**/

这又是公开内容。
```

### 3. 加密所有标记的内容

```bash
python tools/secure_text.py encrypt-notes
```

默认会扫描 `ReadNotes/` 目录下所有 `.md` 文件，找到所有 `/** Encrypt ... **/` 块并加密。

加密后的文件看起来像这样：

```markdown
# 我的笔记

这是公开内容。

/** Encrypt
-----BEGIN CMS-----
MIIBxwYJKoZIhvcNAQcDoIIBuDCCAbQCAQAxggGBMIIBfQIBADBFMDAxLjAsBgNV
BAMMJVJlYWROb3RlcyBMb2NhbCBFbmNyeXB0aW9uIChHZW5lcmF0ZWQpAhEAqvHd
...(更多加密内容)...
-----END CMS-----
**/

这又是公开内容。
```

### 4. 解密查看内容

```bash
python tools/secure_text.py decrypt-notes
```

会将所有加密块还原为明文。

## 高级用法

### 只处理特定文件或目录

```bash
# 只加密某个文件
python tools/secure_text.py encrypt-notes --notes-dir "ReadNotes/一些思考/烦恼和困惑.md"

# 只加密某个子目录
python tools/secure_text.py encrypt-notes --notes-dir "ReadNotes/一些思考"
```

### 使用不同的密钥目录

```bash
python tools/secure_text.py encrypt-notes --key-dir "my-keys"
```

### 加密/解密单个文本或文件

```bash
# 加密文本到文件
echo "敏感信息" | python tools/secure_text.py encrypt-text --out-file secret.enc

# 或者直接指定文本
python tools/secure_text.py encrypt-text --text "敏感信息" --out-file secret.enc

# 解密文件到标准输出
python tools/secure_text.py decrypt-text --in-file secret.enc

# 加密整个文件
python tools/secure_text.py encrypt-file --in-file data.txt --out-file data.enc

# 解密整个文件
python tools/secure_text.py decrypt-file --in-file data.enc --out-file data.txt
```

## 工作流建议

### 日常使用流程

1. **写笔记时**：用 `/** Encrypt ... **/` 标记敏感内容
2. **提交前**：运行 `python tools/secure_text.py encrypt-notes` 加密
3. **提交到 Git**：加密后的文件可以安全提交
4. **需要查看时**：运行 `python tools/secure_text.py decrypt-notes` 解密
5. **查看完毕**：再次加密或直接提交（Git 会显示为未修改）

### 配合 Git 使用

`.gitignore` 已配置忽略 `keys/` 目录，私钥不会被提交。

建议的 Git 工作流：

```bash
# 1. 写完笔记，加密敏感内容
python tools/secure_text.py encrypt-notes

# 2. 查看变更
git diff

# 3. 提交
git add .
git commit -m "更新笔记"
git push

# 4. 需要编辑时，先解密
python tools/secure_text.py decrypt-notes

# 5. 编辑后重新加密
python tools/secure_text.py encrypt-notes
```

### 自动化脚本

可以创建快捷脚本 `encrypt.sh`：

```bash
#!/bin/bash
cd "$(dirname "$0")/.."
python tools/secure_text.py encrypt-notes
echo "✓ 加密完成"
```

和 `decrypt.sh`：

```bash
#!/bin/bash
cd "$(dirname "$0")/.."
python tools/secure_text.py decrypt-notes
echo "✓ 解密完成"
```

## 安全注意事项

1. **私钥保护**：
   - `keys/private_key.pem` 是解密的唯一凭证
   - 务必备份到安全位置（如密码管理器、加密U盘）
   - 不要提交到 Git 或任何公开位置
   - 不要通过不安全的方式传输（如明文邮件、聊天软件）

2. **密钥丢失**：
   - 如果私钥丢失，已加密的内容**无法恢复**
   - 建议定期验证备份的私钥可用

3. **密钥泄露**：
   - 如果私钥泄露，需要：
     1. 立即解密所有内容
     2. 删除旧密钥：`rm -rf keys/`
     3. 重新初始化：`python tools/secure_text.py init`
     4. 重新加密所有内容

4. **加密强度**：
   - 使用 3072 位 RSA 密钥
   - 使用 AES-256-GCM 对称加密
   - 符合现代安全标准

5. **Git 历史**：
   - 加密只保护当前版本
   - Git 历史中可能仍有明文版本
   - 如需彻底清除历史，需要使用 `git filter-branch` 或 BFG Repo-Cleaner

## 幂等性设计

工具设计为**幂等操作**，重复运行不会出错：

- `encrypt-notes` 只加密明文块，跳过已加密的块
- `decrypt-notes` 只解密密文块，跳过已解密的块
- 可以安全地多次运行同一命令

判断依据：块内容是否包含 `-----BEGIN CMS-----`

## 故障排查

### OpenSSL 未找到

```
Error: OpenSSL was not found on PATH.
```

**解决**：安装 OpenSSL 或确保在 PATH 中。

Windows 用户可以：
- 使用 Git Bash（自带 OpenSSL）
- 或安装 OpenSSL for Windows

### 密钥文件缺失

```
Error: Missing private key: keys/private_key.pem. Run: python tools/secure_text.py init
```

**解决**：运行 `python tools/secure_text.py init` 初始化密钥。

### 解密失败

```
Error: ...
```

可能原因：
1. 使用了错误的私钥（不是加密时用的那个）
2. 密文文件损坏
3. OpenSSL 版本不兼容（极少见）

**解决**：
1. 确认使用正确的 `keys/` 目录
2. 从备份恢复文件
3. 检查 OpenSSL 版本：`openssl version`

## 技术细节

### 加密算法

- **非对称加密**：RSA 3072 位
- **对称加密**：AES-256-GCM
- **标准**：OpenSSL CMS (Cryptographic Message Syntax)
- **格式**：PEM (Privacy Enhanced Mail)

### 文件格式

加密块格式：
```
/** Encrypt
-----BEGIN CMS-----
[Base64 编码的 CMS 数据]
-----END CMS-----
**/
```

### 正则表达式

匹配模式：`/\*\* Encrypt[^\n]*\n(.*?)\n\*\*/`（DOTALL 模式）

- 允许 `/** Encrypt` 后跟任意非换行字符（如注释）
- 捕获中间的内容（明文或密文）
- 以 `**/` 结束

## 许可与贡献

这个工具是 ReadNotes 项目的一部分，供个人笔记加密使用。

如有问题或建议，欢迎提 Issue。
