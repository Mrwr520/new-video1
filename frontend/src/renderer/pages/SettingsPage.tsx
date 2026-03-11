import { Link } from 'react-router-dom'

// 设置页 - Python 环境路径和 GPU 配置
export function SettingsPage(): JSX.Element {
  return (
    <div className="page settings-page">
      <h1>设置</h1>
      <p>配置项将在后续任务中实现</p>
      <Link to="/">返回项目列表</Link>
    </div>
  )
}
