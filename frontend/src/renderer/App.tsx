import { HashRouter, Routes, Route } from 'react-router-dom'
import { ProjectListPage } from './pages/ProjectListPage'
import { ProjectWorkbench } from './pages/ProjectWorkbench'
import { TextInputPage } from './pages/TextInputPage'
import { CharacterManagePage } from './pages/CharacterManagePage'
import { StoryboardPage } from './pages/StoryboardPage'
import { VideoPreviewPage } from './pages/VideoPreviewPage'
import { SettingsPage } from './pages/SettingsPage'
import { ModelManagePage } from './pages/ModelManagePage'
import { ScriptOptimizationView } from '../views/ScriptOptimizationView'

export function App(): JSX.Element {
  return (
    <HashRouter>
      <Routes>
        {/* 项目列表页 */}
        <Route path="/" element={<ProjectListPage />} />

        {/* 项目工作台 */}
        <Route path="/project/:id" element={<ProjectWorkbench />} />

        {/* 项目子页面 */}
        <Route path="/project/:id/text" element={<TextInputPage />} />
        <Route path="/project/:id/chars" element={<CharacterManagePage />} />
        <Route path="/project/:id/story" element={<StoryboardPage />} />
        <Route path="/project/:id/preview" element={<VideoPreviewPage />} />

        {/* 设置页 */}
        <Route path="/settings" element={<SettingsPage />} />

        {/* 模型管理页 */}
        <Route path="/models" element={<ModelManagePage />} />

        {/* 剧本迭代优化 */}
        <Route path="/project/:id/script-optimization" element={<ScriptOptimizationView />} />
      </Routes>
    </HashRouter>
  )
}
