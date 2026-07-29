import type { MethodologySectionContent } from "@/lib/content/methodology-sections";
import { TechnicalDetails } from "./TechnicalDetails";
import styles from "./MethodologySection.module.css";

export interface MethodologySectionProps {
  section: MethodologySectionContent;
}

export function MethodologySection({ section }: MethodologySectionProps) {
  return (
    <section className={styles.section} aria-labelledby={`methodology-${section.id}`}>
      <h2 className={styles.heading} id={`methodology-${section.id}`}>
        {section.title}
      </h2>
      {section.paragraphs.map((paragraph, index) => (
        <p className={styles.paragraph} key={index}>
          {paragraph}
        </p>
      ))}
      {section.technicalDetails && section.technicalDetails.length > 0 && (
        <TechnicalDetails summary="Technical detail">
          {section.technicalDetails.map((detail, index) => (
            <p key={index}>{detail}</p>
          ))}
        </TechnicalDetails>
      )}
    </section>
  );
}
