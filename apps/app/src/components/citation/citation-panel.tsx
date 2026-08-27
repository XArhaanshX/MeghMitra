import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { hasValidCitation } from '@/schemas';
import type { Citation } from '@/schemas';

interface CitationPanelProps {
  citation: Citation | null | undefined;
  isLoading?: boolean;
  heading?: string;
}

// The brand moment: proof that a recommendation traces back to an exact
// page of a real DACP document. Reused on the rule detail page and the
// evaluate result panel -- keep both call sites visually identical.
export function CitationPanel({
  citation,
  isLoading = false,
  heading = 'Source citation',
}: CitationPanelProps) {
  return (
    <Card className="bg-sand-50 shadow-[4px_4px_0_0_var(--ink)]">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-mono text-xs font-bold tracking-widest text-teal-deep uppercase">
          <span className="size-2 shrink-0 rounded-full bg-teal" />
          {heading}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {isLoading && <p className="text-sm text-ink-muted">Loading citation</p>}
        {!isLoading && (!citation || !hasValidCitation(citation)) && (
          <p className="text-sm text-ink-muted">No valid citation on file.</p>
        )}
        {citation && hasValidCitation(citation) && (
          <>
            <p className="font-mono text-lg font-bold text-ink">{citation.document}</p>
            <p className="font-mono text-sm text-ink-soft">
              {citation.bounding_region ? `${citation.bounding_region}, ` : ''}p. {citation.page}
            </p>
            {citation.source_text && (
              <blockquote className="border-l-2 border-teal pl-3 text-sm text-ink-muted italic">
                &ldquo;{citation.source_text}&rdquo;
              </blockquote>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
