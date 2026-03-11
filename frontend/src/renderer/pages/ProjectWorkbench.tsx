import { useParams, Link } from 'react-router-dom'

// 项目工作台 - 项目的主工作区
export function ProjectWorkbench(): JSX.Element {
  const { id } = useParams<{ id: string }>()

  return (
    <div className="page project-workbench">
      <h1>项目工作台</h1>
      <p>项目 ID: {id}</p>
      <nav>
        <Link to={`/project/${id}/text`}>文本输入</Link>
        <Link to={`/project/${id}/chars`}>角色管理</Link>
        <Link to={`/project/${id}/story`}>分镜编辑</Link>
        <Link to={`/project/${id}/preview`}>视频预览</Link>
      </nav>
      <Link to="/">返回项目列表</Link>
    </div>
  )
}
