/** 页内工具条：不重复顶栏标题 */
export default function PageHead({ children, extra }) {
  if (!children && !extra) return null
  return (
    <div className="page-toolbar">
      {children ? <p className="page-toolbar-note">{children}</p> : <span />}
      {extra ? <div className="page-toolbar-extra">{extra}</div> : null}
    </div>
  )
}
