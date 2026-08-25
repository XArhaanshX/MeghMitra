import { mergeProps } from '@base-ui/react/merge-props';
import { useRender } from '@base-ui/react/use-render';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'group/badge inline-flex h-6 w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-sm border-2 border-transparent px-2.5 py-0.5 font-mono text-xs font-bold tracking-wide whitespace-nowrap uppercase transition-all focus-visible:ring-[3px] focus-visible:ring-ring/50 has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 aria-invalid:border-destructive aria-invalid:ring-destructive/20 [&>svg]:pointer-events-none [&>svg]:size-3!',
  {
    variants: {
      variant: {
        default: 'border-ink bg-primary text-primary-foreground [a]:hover:bg-primary/80',
        secondary: 'border-ink bg-secondary text-secondary-foreground [a]:hover:bg-secondary/80',
        destructive:
          'border-ink bg-destructive text-destructive-foreground [a]:hover:bg-destructive/80',
        outline: 'border-ink bg-background text-foreground [a]:hover:bg-muted',
        ghost: 'border-transparent text-muted-foreground hover:bg-muted hover:text-foreground',
        link: 'border-transparent text-primary underline-offset-4 hover:underline',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
);

function Badge({
  className,
  variant = 'default',
  render,
  ...props
}: useRender.ComponentProps<'span'> & VariantProps<typeof badgeVariants>) {
  return useRender({
    defaultTagName: 'span',
    props: mergeProps<'span'>(
      {
        className: cn(badgeVariants({ variant }), className),
      },
      props
    ),
    render,
    state: {
      slot: 'badge',
      variant,
    },
  });
}

export { Badge, badgeVariants };
