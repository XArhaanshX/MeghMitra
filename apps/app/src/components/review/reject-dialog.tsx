'use client';

import { useState } from 'react';
import { toast } from 'sonner';

import { isApiError } from '@/api';
import { useRejectRule } from '@/api/review-hooks';
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
import { Textarea } from '@/components/ui/textarea';
import { useZodForm } from '@/hooks/use-zod-form';
import { rejectFormSchema } from '@/schemas';
import type { RejectFormValues } from '@/schemas';

interface RejectDialogProps {
  ruleId: string;
}

export function RejectDialog({ ruleId }: RejectDialogProps) {
  const [open, setOpen] = useState(false);
  const rejectRule = useRejectRule();
  const form = useZodForm(rejectFormSchema, { defaultValues: { reviewed_by: '', reason: '' } });

  async function onSubmit(values: RejectFormValues) {
    try {
      await rejectRule.mutateAsync({
        id: ruleId,
        body: { reviewed_by: values.reviewed_by, reason: values.reason || undefined },
      });
      toast.success('Rule rejected.');
      setOpen(false);
      form.reset();
    } catch (error) {
      toast.error(isApiError(error) ? error.message : 'Failed to reject rule.');
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button size="sm" variant="destructive">
            Reject
          </Button>
        }
      />
      <DialogContent>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Reject rule</DialogTitle>
            <DialogDescription>
              The extraction is wrong or unusable. This rule stays out of the advisory-eligible set.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="reject-reviewed-by">Your name</Label>
            <Input id="reject-reviewed-by" {...form.register('reviewed_by')} autoFocus />
            {form.formState.errors.reviewed_by && (
              <p className="text-sm text-destructive">
                {form.formState.errors.reviewed_by.message}
              </p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="reject-reason">Reason (optional)</Label>
            <Textarea id="reject-reason" rows={3} {...form.register('reason')} />
          </div>
          <DialogFooter>
            <Button type="submit" variant="destructive" disabled={rejectRule.isPending}>
              {rejectRule.isPending ? 'Rejecting…' : 'Confirm rejection'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
