/** 页面标题旁的「必做/常用/进阶」说明 */
export default function PageIntro({ title, need, children, extra }) {
  const tag =
    need === '必做' ? 'need-tag--must' : need === '常用' ? 'need-tag--common' : 'need-tag--adv'
  return (
    <div className="page-head">
      <div>
        <div className="need-row">
          <h2>{title}</h2>
          <span className={`need-tag ${tag}`}>{need}</span>
        </div>
        <p>{children}</p>
      </div>
      {extra}
    </div>
  )
}
