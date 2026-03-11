import { useParams, Link } from 'react-router-dom'

// 视频预览页 - 预览生成的视频片段和最终视频
export function VideoPreviewPage(): JSX.Element {
  const { id } = useParams<{ id: string }>()

  return (
    <div className="page video-preview-page">
      <h1>视频预览</h1>
      <p>项目 ID: {id}</p>
      <Link to={`/project/${id}`}>返回工作台</Link>
    </div>
  )
}
