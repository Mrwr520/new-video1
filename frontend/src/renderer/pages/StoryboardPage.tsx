import { useParams, Link } from 'react-router-dom'

// 分镜编辑页 - 时间线视图展示和编辑分镜脚本
export function StoryboardPage(): JSX.Element {
  const { id } = useParams<{ id: string }>()

  return (
    <div className="page storyboard-page">
      <h1>分镜编辑</h1>
      <p>项目 ID: {id}</p>
      <Link to={`/project/${id}`}>返回工作台</Link>
    </div>
  )
}
