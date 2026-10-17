# 多人协作说明

本文件说明 `m-tx25/chuangzhibei` 这个仓库在多人协作下的前提条件、推荐设置和日常操作流程。

---

## 一、当前仓库状态（实测）

| 项目 | 现状 | 说明 |
| --- | --- | --- |
| 仓库 | `m-tx25/chuangzhibei` | 个人账号（User）名下，非组织 |
| 可见性 | **公开（public）** | 任何人都能查看、克隆、Fork |
| 默认分支 | `main` | 当前 `ff1db8a` |
| 分支保护 | **未设置** | 任何人拿到写权限都能直接 push，甚至强推/删除 main |
| 协作者 | 除 owner 外**尚未添加** | 需 owner 主动邀请 |
| Issues | 已启用 | 可用于派活、记录 bug |
| Discussions | 未启用 | 如需讨论区要在 Settings 打开 |
| Wiki / Pages | 未启用 | |
| Actions / CI | **未配置** | 没有任何自动化检查 |
| 仓库内密钥 | 无 | `.gitignore` 已排除 `.env`、`*.pem` |

### 由此推出的两条关键前提

1. **想让人协作，必须由 owner（m-tx25）在网页上发出邀请。** 个人仓库没有"只读协作者"这个选项，被邀请的人拿到的是**读写权限**——能直接改 `main`。
2. **当前公开 + 无保护 = 谁都能改主干。** 在拉人进来之前，建议先设好分支保护规则，否则误操作或强推会直接丢掉提交，而且没法从 GitHub 侧限制。

---

## 二、协作模式：先选一种

### 模式 A：添加协作者（适合 2–5 人的参赛小队）

所有人直接对同一个仓库有写权限，靠分支 + PR 来隔离改动。

- 优点：无需 Fork，推送直接进主仓库，协作最省事
- 缺点：个人仓库只能给"读写"权限，没有更细的粒度；要细粒度得把仓库转到 organization

### 模式 B：Fork + Pull Request（适合对外开放、或不想给写权限时）

别人 Fork 出自己的一份，改完提 PR 给你合。**当前仓库是 public，所以任何 GitHub 用户现在就能这么做，不需要你做任何设置。**

- 优点：你不必给任何人写权限，改动必须经你审查
- 缺点：Fork 的同步、PR 的来回会多一些步骤

> 小队伍用 A；拉外部人、或者只是想让别人贡献代码用 B。

---

## 三、Owner 一次性配置

### 3.1 邀请协作者（模式 A）

1. 打开 <https://github.com/m-tx25/chuangzhibei/settings/access>
2. 点 **Add people** → 输入对方的 GitHub 用户名或注册邮箱
3. 选择权限（个人仓库只有 **Read / Write / Admin**，选 **Write**）
4. 点 **Add … to this repository**

对方会收到邮件/通知，**必须点接受**才真正生效（在此之前他在 `Settings → Collaborators` 里显示为 pending）。

> ⚠️ 注意：GitHub Free 对**私人**仓库的协作者给了只读档位，但**个人账号的公开仓库**邀请协作者时给的就是写权限。如果你希望有人只能看不能改，只能用模式 B（Fork）。

### 3.2 保护 main 分支（强烈建议，公开仓库免费）

本仓库是 public，所以即使免费账号也能用分支保护 / 规则集。

**方式一：规则集（Rulesets，GitHub 现在推荐的方式）**

1. <https://github.com/m-tx25/chuangzhibei/settings/rules> → **New ruleset** → **New branch ruleset**
2. Name 填 `protect-main`，Enforcement status 选 **Active**
3. Target branches → **Add target** → **Include default branch**
4. 勾选规则：
   - ✅ **Restrict deletions**：禁止删除 main
   - ✅ **Block force pushes**：禁止强推覆盖历史
   - ✅ **Require a pull request before merging**（该项下再勾 **Require approvals** = 1）
5. （可选）Bypass list 里把自己加进去，方便紧急情况；不加则对所有人一律生效
6. **Create**

**方式二：经典分支保护规则（Branch protection rule）**

<https://github.com/m-tx25/chuangzhibei/settings/branches> → **Add branch protection rule** → Branch name pattern 填 `main` → 勾选：

- **Require a pull request before merging** → Require approvals: 1
- **Do not allow bypassing the above settings**（按需）
- **Restrict who can push to matching branches**（按需）

> 说明：官方文档指出"必需 PR 审查"在多分支/私有仓库场景属于付费能力，但**公开仓库免费可用**；规则集与经典保护规则可以同时存在，同时命中时**取更严格的那条**。

### 3.3 其它建议

- **开 Discussions**：`Settings → General → Features → Discussions`，适合讨论方案而不污染 Issues
- **关掉不用的功能**：Wiki、Projects 按需
- **私有化判断**：如果比赛材料/题面不适合公开，立刻在 `Settings → General → Danger Zone → Change visibility` 改为 Private；但注意私有仓库的"必需审查""保护分支"在免费账号下不可用（需 Pro），且私有仓库的协作者只有写权限
- **转组织**：如果人多或需要"只读成员 / 分组权限"，新建一个 free organization 把仓库转过去，就能用 Team 级别的权限控制了

---

## 四、协作者本机一次性配置

每个协作者在自己电脑上做一次即可。

```bash
# 1) 克隆（模式 A：有写权限，直接克隆主仓库）
git clone https://github.com/m-tx25/chuangzhibei.git
cd chuangzhibei

# 2) 设置自己的身份（重要！否则提交作者是别人的名字）
git config user.name "你的名字"
git config user.email "你的邮箱或 GitHub noreply 邮箱"

# 3) 确认远端
git remote -v
```

**模式 B（无写权限）则用 Fork：**

```bash
# 网页上先点 Fork，然后克隆自己的那份
git clone https://github.com/<你的用户名>/chuangzhibei.git
cd chuangzhibei
git remote add upstream https://github.com/m-tx25/chuangzhibei.git
```

> ⚠️ **注意**：仓库里 `README.md` 记录的 SteamTools / CA 证书配置是 **owner 本机**的环境适配，**不要照抄**。
> 协作者只有在同样装了 SteamTools 之类做 TLS 中间人的加速器、导致 git 报
> `unable to get local issuer certificate` 时，才需要做类似配置。

---

## 五、日常协作流程（核心）

**铁律：不要直接往 `main` 提交。** 所有改动走"功能分支 → 推送 → PR → 审查 → 合并"。

```bash
# 1) 每次开工前，先同步最新 main
git switch main
git pull

# 2) 开一个功能分支（名字别用中文/空格）
git switch -c feat/login-page

# 3) 改代码，小步提交
git add -A
git commit -m "feat: 新增登录页表单校验"

# 4) 推送分支（首次要 -u）
git push -u origin feat/login-page

# 5) 在网页上开 PR
#    https://github.com/m-tx25/chuangzhibei/compare
#    base: main   ←   compare: feat/login-page
#    填标题和说明，指派审查人，然后 Create pull request

# 6) 审查通过后，网页上点 Merge pull request
#    合并后删掉远端分支（网页上有按钮）
git switch main
git pull
git branch -d feat/login-page
```

### 分支命名约定（建议）

| 前缀 | 用途 | 例子 |
| --- | --- | --- |
| `feat/` | 新功能 | `feat/user-profile` |
| `fix/` | 修 bug | `fix/login-500` |
| `docs/` | 文档 | `docs/deploy-guide` |
| `refactor/` | 重构 | `refactor/api-layer` |

### 提交信息约定（建议，Conventional Commits）

```
feat: 新功能
fix: 修复缺陷
docs: 只改文档
refactor: 重构（不改行为）
chore: 构建/依赖/杂项
```

---

## 六、最常见的三个麻烦

### 6.1 冲突（同一文件两人都改了）

PR 页面会提示 "This branch has conflicts that must be resolved"。在本地解决：

```bash
git switch main
git pull
git switch 你的分支
git merge main          # 或者 git rebase main
# 打开冲突文件，找 <<<<<<< ======= >>>>>>> 标记，改成你想要的内容
git add 冲突文件
git commit              # rebase 的话用 git rebase --continue
git push
```

**不要**用 `git push --force` 解决冲突——那会把别人已合并的提交抹掉。万不得已要强推自己的分支时，也只用：
`git push --force-with-lease`（它会先检查远端有没有别人的新提交）。

### 6.2 提交作者写错了（显示成别人的名字）

```bash
# 只改最近一次提交的作者
git commit --amend --author="你的名字 <你的邮箱>" --no-edit
```

### 6.3 不小心把密码/密钥提交上去了

**立刻当作已泄露处理**：

1. 马上去对应平台**作废/轮换**这把密钥（改密码、Revoke Token）
2. 再清理仓库历史（`git filter-repo` 或联系 GitHub Support），否则历史里永远查得到
3. 检查 `.gitignore` 是否覆盖了该类文件

---

## 七、账号与凭证：不要共用

| 做法 | 评价 |
| --- | --- |
| 每人用自己的 GitHub 账号 + 自己的 Token/SSH Key | ✅ 正确。提交记录能追溯到人，出问题能单独收回权限 |
| 全队共用一个账号 / 共用一把 Token | ❌ 错误。无法审计、一人泄露全队遭殃、GitHub 也可能判定异常 |
| 把 Token 写进仓库文件或提交进历史 | ❌ 严禁。公开仓库等于全世界可见，会被爬虫秒扫 |

### 用 Token 推送（HTTPS）

细粒度令牌（Fine-grained token）需在 <https://github.com/settings/personal-access-tokens> 创建：

- **Repository access**：选 *Only select repositories* → 勾 `m-tx25/chuangzhibei`
- **Permissions → Repository permissions**：
  - `Contents: Read and write`（推送必需）
  - 需要建仓库/改设置才要 `Administration`
- 有效期建议设短一些

推送时把它当密码填，或者让 git 记住：

```bash
# 推荐：用凭据管理器保存（Windows 上 Git for Windows 自带）
git config --global credential.helper manager
# 第一次 push 会弹浏览器授权，之后不用再输
```

### 用 SSH 推送

```bash
ssh-keygen -t ed25519 -C "你的邮箱"
# 把 ~/.ssh/id_ed25519.pub 的内容粘到 https://github.com/settings/keys
ssh -T git@github.com          # 看到 "Hi <用户名>!" 就成功了
git remote set-url origin git@github.com:m-tx25/chuangzhibei.git
```

> 若本机装了 SteamTools 一类加速器导致 `ssh github.com` 被劫持到 `127.0.0.1`，
> 可改用 443 端口：在 `~/.ssh/config` 加
> `Host github.com` / `Hostname ssh.github.com` / `Port 443` / `User git`。

---

## 八、上线前检查清单

- [ ] owner 已邀请全部成员，且成员**已接受**邀请
- [ ] `main` 已设置规则集或分支保护：禁止强推、禁止删除、要求 PR
- [ ] 每位成员都设置了自己的 `user.name` / `user.email`
- [ ] 仓库内无密钥、无 `.env`、无个人隐私数据（公开仓库尤其重要）
- [ ] `.gitignore` 覆盖了依赖目录、构建产物、IDE 配置
- [ ] 确认仓库可见性（公开 / 私有）符合比赛要求
- [ ] 约定好分支命名与提交信息规范（本文档第五节的建议可直接用）
- [ ] 明确谁负责合并 PR、谁负责发版

---

## 参考

- [邀请协作者到个人仓库](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository)
- [个人账号仓库的权限级别](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/permission-levels-for-a-personal-account-repository)
- [关于规则集](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)
- [关于分支保护](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [Pull Request 快速上手](https://docs.github.com/en/pull-requests/get-started/pull-request-quickstart)
- [GitHub 各版本方案对比](https://docs.github.com/en/get-started/learning-about-github/githubs-plans)
