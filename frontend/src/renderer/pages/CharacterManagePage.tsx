import { useParams, Link } from 'react-router-dom'

// 角色管理页 - 查看和编辑提取的角色信息
export function CharacterManagePage(): JSX.Element {
  const { id } = useParams<{ id: string }>()

  return (
    <div className="page character-manage-page">
      <h1>角色管理</h1>
      <p>项目 ID: {id}</p>
      <Link to={`/project/${id}`}>返回工作台</Link>
    </div>
  )
}
