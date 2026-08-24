'use client';

import { standardSchemaResolver } from '@hookform/resolvers/standard-schema';
import type { FieldValues, Resolver, UseFormProps, UseFormReturn } from 'react-hook-form';
import { useForm } from 'react-hook-form';
import type { infer as ZodInfer, ZodType } from 'zod';

// standardSchemaResolver's Input/Output split doesn't nominally unify with
// react-hook-form's single-TFieldValues UseFormProps when a schema has no
// `.transform()` (Input and Output are structurally identical here, just not
// nominally, per react-hook-form/resolvers#813/#842) -- the cast below is
// scoped to exactly that resolver boundary, nothing else in this file.
export function useZodForm<TSchema extends ZodType<FieldValues, FieldValues>>(
  schema: TSchema,
  options?: Omit<UseFormProps<ZodInfer<TSchema>>, 'resolver'>
): UseFormReturn<ZodInfer<TSchema>> {
  return useForm<ZodInfer<TSchema>>({
    ...options,
    resolver: standardSchemaResolver(schema) as Resolver<ZodInfer<TSchema>>,
  });
}
