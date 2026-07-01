type SectionHeadingProps = {
  title: string;
  text?: string;
  align?: "left" | "center";
};

export function SectionHeading({ title, text, align = "left" }: SectionHeadingProps) {
  return (
    <div className={align === "center" ? "mx-auto max-w-3xl text-center" : "max-w-3xl"}>
      <h2 className="font-display text-3xl font-bold tracking-normal text-white sm:text-4xl">
        {title}
      </h2>
      {text ? <p className="mt-4 text-base leading-7 text-clinic-muted sm:text-lg">{text}</p> : null}
    </div>
  );
}
