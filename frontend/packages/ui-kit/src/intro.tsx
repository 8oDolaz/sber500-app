import { useEffect, type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode } from "react";
import { Button, Screen } from "./components";
import mascot from "./assets/intro/mascot.png";
import telegram from "./assets/intro/telegram.svg";
import forwardMessage from "./assets/intro/forward-message.png";
import forwardMenu from "./assets/intro/forward-menu.png";
import botSearch from "./assets/intro/bot-search.png";
import botResult from "./assets/intro/bot-result.png";
import photoResult from "./assets/intro/photo-result.png";
import familyPlan from "./assets/intro/family-plan.png";
import arrow from "./assets/intro/arrow.svg";
import invitePerson from "./assets/intro/invite-person.svg";

export function IntroPage({ children, ...props }: HTMLAttributes<HTMLElement>) {
  useEffect(() => {
    const theme = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
    const previous = theme?.content;
    if (theme) theme.content = "#000000";
    return () => { if (theme && previous !== undefined) theme.content = previous; };
  }, []);
  return <Screen variant="home" className="kn-screen--intro" {...props}>{children}</Screen>;
}

export function IntroInviteIcon() {
  return <span className="kn-home-icon kn-home-icon--invitePerson" aria-hidden="true"><img src={invitePerson} alt="" /></span>;
}

export function IntroBrand() {
  return <div className="kn-intro-brand" aria-label="kainem">
    <span className="kn-intro-brand__icon" aria-hidden="true"><img src={mascot} alt="" /></span>
    <span className="kn-intro-brand__name" aria-hidden="true">kainem</span>
  </div>;
}

export function IntroHero({ title, description, navigation, action, caption }: {
  title: ReactNode; description: string; navigation?: ReactNode; action?: ReactNode; caption?: string;
}) {
  return <header className={`kn-intro-hero ${navigation ? "kn-intro-hero--guide" : ""}`}>
    {navigation && <nav aria-label="Навигация">{navigation}</nav>}
    <IntroBrand />
    <div className="kn-intro-intro"><h1>{title}</h1><p>{description}</p></div>
    {action && <div className="kn-intro-actions">{action}{caption && <p className="kn-intro-caption">{caption}</p>}</div>}
  </header>;
}

export function IntroAction({ telegramIcon = true, loading, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { telegramIcon?: boolean; loading?: boolean }) {
  return <Button {...props} loading={loading} className="kn-intro-action">
    {loading ? <span className="kn-intro-spinner" aria-hidden="true" /> : telegramIcon && <span className="kn-intro-telegram" aria-hidden="true"><img src={telegram} alt="" /></span>}
    <span>{children}</span>
  </Button>;
}

export function IntroBack(props: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type="button" {...props} className="kn-intro-back" />;
}

export function IntroSection({ title, children }: { title: string; children: ReactNode }) {
  return <section className="kn-intro-section"><h2>{title}</h2>{children}</section>;
}

export function IntroCard({ children, className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={`kn-intro-card ${className}`}>{children}</div>;
}

/** The individual Figma image fills retain their original crops. Text remains HTML. */
export function ForwardExample() {
  return <figure className="kn-intro-figure kn-intro-forward" aria-label="Пример: пересылка сообщения в Telegram боту kainem">
    <div className="kn-intro-crop kn-intro-forward__message"><img src={forwardMessage} loading="lazy" alt="" /></div>
    <div className="kn-intro-crop kn-intro-forward__menu"><img src={forwardMenu} loading="lazy" alt="" /></div>
    <span className="kn-intro-forward__arrow kn-intro-forward__arrow--first" aria-hidden="true"><img src={arrow} alt="" /></span>
    <div className="kn-intro-crop kn-intro-forward__search"><img src={botSearch} loading="lazy" alt="" /></div>
    <div className="kn-intro-crop kn-intro-forward__bot"><img src={botSearch} loading="lazy" alt="" /></div>
    <span className="kn-intro-forward__arrow kn-intro-forward__arrow--second" aria-hidden="true"><img src={arrow} alt="" /></span>
    <div className="kn-intro-crop kn-intro-forward__result"><img src={botResult} loading="lazy" alt="" /></div>
  </figure>;
}

export function PhotoExample() {
  return <figure className="kn-intro-figure kn-intro-photo" aria-label="Пример: бот распознаёт запись на приём из скриншота">
    <div className="kn-intro-crop"><img src={photoResult} loading="lazy" alt="" /></div>
  </figure>;
}

export function PlanExample({ cropped = false }: { cropped?: boolean }) {
  return <figure className={`kn-intro-plan ${cropped ? "kn-intro-plan--cropped" : ""}`} aria-label="Пример главной: задачи, события и дела на сегодня">
    <img src={familyPlan} loading="lazy" alt="" />
  </figure>;
}

export function IntroTutorial({ variant = "guide" }: { variant?: "welcome" | "guide" }) {
  const welcome = variant === "welcome";
  return <IntroSection title={welcome ? "Как пользоваться" : "Как добавить дело"}>
    <IntroCard className="kn-intro-tutorial">
      <section className="kn-intro-step">
        <h3>{welcome ? <>1. Перешлите сообщение<br />из чата боту</> : "Перешлите сообщение из чата"}</h3>
        <p>{welcome ? "Отправьте боту текст, фото или скриншот с семейными делами." : "В чате нажмите «Переслать» и выберите бота kainem. Можно также написать ему напрямую."}</p>
        <ForwardExample />
      </section>
      <section className="kn-intro-step">
        <h3 className={welcome ? "kn-intro-numbered" : undefined}>{welcome && <span>2.</span>}<span>Или отправьте фото или скриншот</span></h3>
        <p>{welcome ? "kainem распознает текст и предложит задачу или событие." : "Отправьте изображение боту. Он распознает текст и предложит задачу или событие."}</p>
        <PhotoExample />
      </section>
      <section className="kn-intro-step">
        <h3 className={welcome ? "kn-intro-numbered" : undefined}>{welcome && <span>3.</span>}<span>{welcome ? "Проверьте запись и сохраните" : "Проверьте и сохраните"}</span></h3>
        <p>{welcome ? "Проверьте дату, время и человека в боте. После подтверждения запись появится в плане семьи." : "Проверьте дату, время и человека в боте. Подтвердите запись — она появится на главной."}</p>
        <PlanExample cropped={welcome} />
      </section>
    </IntroCard>
  </IntroSection>;
}

export function IntroFeatures() {
  return <IntroSection title="Планируем добавить"><div className="kn-intro-features">
    <IntroCard><h3>Управление через Алису</h3><p>Планируем добавление семейных дел голосом.</p></IntroCard>
    <IntroCard><h3>Подключение календаря</h3><p>Планируем синхронизацию семейных событий с календарём.</p></IntroCard>
  </div></IntroSection>;
}

export function IntroHomeGuide({ blocks }: { blocks: readonly { title: string; text: string }[] }) {
  return <IntroSection title="Что есть на главной"><IntroCard className="kn-intro-home-guide">
    {blocks.map(block => <section key={block.title}><h3>{block.title}</h3><p>{block.text}</p></section>)}
  </IntroCard></IntroSection>;
}
