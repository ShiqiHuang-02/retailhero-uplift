# Git 与 GitHub：这个项目的版本管理

Git 保存本机的改动历史；GitHub 保存推送到远端的 Git 提交。首次目标是主分支 `main` 的一个完整提交，并以 `v0.1.0` 标记这一状态。

## 第一版包含什么

提交 notebook、Python 与 SQL 源码、测试、依赖清单、JSON 配置、说明文档和汇总展示材料。现有 notebook 包含保存的运行输出及少量数据示例，阅读或公开前应了解其内容。

`.gitignore` 排除 `.venv/`、原始数据、processed 数据、客户名单 `assignments.csv`、客户级 Parquet、模型 joblib、随机抽样数组和 `work/` 备份。忽略不等于删除，这些文件继续保留在本机。

保留 `data/splits/metadata.json` 作为名单校验与来源记录；它不能替代名单本身。仅克隆代码仓库无法复现全部结果，还需要合法取得原始数据，并从自己的备份恢复对应名单。模型通过训练流程重新生成。不要将 `.venv` 当作可跨电脑复制的环境。

## 首次提交和推送

在 GitHub 创建空仓库时，不额外初始化 README、.gitignore 或 License，因为本地已有项目内容。仓库可以先设为 Private，整理好展示内容后再自行决定是否公开。

Git 提交需要作者姓名与邮箱；它们不是登录凭据。可使用 GitHub 提供的 noreply 邮箱。以下姓名、邮箱和 URL 都要换成自己的真实值，不能原样运行占位符。

```bash
# 在项目根目录配置本项目的提交署名
git config user.name "你的提交署名"
git config user.email "你的提交邮箱"

# 查看将提交的文件和变更
git status
git diff --cached --stat

# 建立首个记录和版本标签
git commit -m "chore: establish v0.1.0 project baseline"
git tag -a v0.1.0 -m "First portfolio baseline"

# 关联已经创建的空仓库并上传
git remote add origin https://github.com/你的用户名/retailhero-uplift.git
git push -u origin main
git push origin v0.1.0
```

若 `origin` 已存在，先 `git remote -v` 检查，不要重复添加或直接覆盖。GitHub 身份验证由本机 Git/编辑器登录流程处理，不把密码或 token 放进代码、仓库 URL 或聊天中。

## 以后每次修改

先完成一个明确的小任务，再检查和提交。例如更新研究说明：

```bash
git status
git diff -- README.md docs/research_design.md
git add README.md docs/research_design.md
git diff --cached
git commit -m "docs: clarify causal identification assumptions"
git push
```

完成代码或模型逻辑修改后，先运行相应检查，再提交代码、文档和确实要更新的汇总结果。避免为一次文字修改提交整批无关的 notebook 输出变化。

查看历史使用 `git log --oneline --decorate`。`v0.1.0` 标签保持指向第一版，不随后续修改移动。下一阶段完成后再创建 `v0.2.0`，日常小修改只需普通 commit。

`.gitignore` 只阻止尚未跟踪的文件被自动加入；如果误提交了数据文件，后续添加忽略规则并不会自动清除其 Git 历史。

官方参考：[将本地代码添加到 GitHub](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)。
