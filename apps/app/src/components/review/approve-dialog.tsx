'use client';

import { useState } from 'react';
import { toast } from 'sonner';

import { isApiError } from '@/api';
import { useApproveRule } from '@/api/review-hooks';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useZodForm } from '@/hooks/use-zod-form';
import { approveFormSchema } from '@/schemas';
import type { ApproveFormValues } from '@/schemas';

interface ApproveDialogProps {
  ruleId: string;
  disabled?: boolean;
}

// Confidence never gates this -- a human can approve a low-confidence rule
// after checking the source page. The only server-side gate is citation
// validity (422 `detail` is surfaced verbatim below, e.g. "cannot approve a
// rule without a valid citation" or a page-out-of-range message).
export function ApproveDialog({ ruleId, disabled }: ApproveDialogProps) {
  const [open, setOpen] = useState(false);
  const approveRule = useApproveRule();
  const form = useZodForm(approveFormSchema, { defaultValues: { reviewed_by: '' } });

  async function onSubmit(values: ApproveFormValues) {
    try {
      await approveRule.mutateAsync({ id: ruleId, body: values });
      toast.success('Rule approved.');
      setOpen(false);
      form.reset();
    } catch (error) {
      toast.error(isApiError(error) ? error.message : 'Failed to approve rule.');
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button size="sm" disabled={disabled}>
            Approve
          </Button>
        }
      />
      <DialogContent>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Approve rule</DialogTitle>
            <DialogDescription>
              Confirms this rule matches its source document. Only approved rules become eligible
              for automated advisory output.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="approve-reviewed-by">Your name</Label>
            <Input id="approve-reviewed-by" {...form.register('reviewed_by')} autoFocus />
            {form.formState.errors.reviewed_by && (
              <p className="text-sm text-destructive">
                {form.formState.errors.reviewed_by.message}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button type="submit" disabled={approveRule.isPending}>
              {approveRule.isPending ? 'Approving…' : 'Confirm approval'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
