/**
 * 最小 JSON Schema 校验器，供测试使用。
 *
 * 不引入运行时依赖，只覆盖本工程 schema 用到的关键字：
 * type、enum、required、properties、additionalProperties、items、
 * minLength、maxLength、pattern、format=date-time、minimum。
 */

import { readFile } from "node:fs/promises";

export type JsonSchema = Record<string, unknown>;

function typeOf(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  if (Number.isInteger(value)) return "integer";
  return typeof value;
}

function matchesType(value: unknown, expected: string): boolean {
  const actual = typeOf(value);
  if (expected === "number") return actual === "number" || actual === "integer";
  if (expected === "integer") return actual === "integer";
  return actual === expected;
}

export function validateJsonSchema(
  value: unknown,
  schema: JsonSchema,
  path = "$",
): string[] {
  const errors: string[] = [];
  const types = schema.type;
  if (typeof types === "string") {
    if (!matchesType(value, types)) errors.push(`${path}: 期望 ${types}，实际 ${typeOf(value)}`);
  } else if (Array.isArray(types)) {
    if (!types.some((type) => typeof type === "string" && matchesType(value, type))) {
      errors.push(`${path}: 期望 ${types.join("|")}，实际 ${typeOf(value)}`);
    }
  }

  const enumValues = schema.enum;
  if (Array.isArray(enumValues) && !enumValues.some((item) => item === value)) {
    errors.push(`${path}: 值 ${String(value)} 不在枚举内`);
  }

  if (typeof value === "string") {
    if (typeof schema.minLength === "number" && value.length < schema.minLength) {
      errors.push(`${path}: 长度小于 ${schema.minLength}`);
    }
    if (typeof schema.maxLength === "number" && value.length > schema.maxLength) {
      errors.push(`${path}: 长度大于 ${schema.maxLength}`);
    }
    if (typeof schema.pattern === "string" && !new RegExp(schema.pattern).test(value)) {
      errors.push(`${path}: 不匹配 ${schema.pattern}`);
    }
    if (schema.format === "date-time" && Number.isNaN(Date.parse(value))) {
      errors.push(`${path}: 不是合法 date-time`);
    }
  }

  if (typeof value === "number" && typeof schema.minimum === "number" && value < schema.minimum) {
    errors.push(`${path}: 小于最小值 ${schema.minimum}`);
  }

  if (Array.isArray(value) && schema.items && typeof schema.items === "object") {
    value.forEach((item, index) => {
      errors.push(...validateJsonSchema(item, schema.items as JsonSchema, `${path}[${index}]`));
    });
  }

  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    const properties = (schema.properties ?? {}) as Record<string, JsonSchema>;
    for (const name of (schema.required ?? []) as string[]) {
      if (!(name in record)) errors.push(`${path}: 缺少必填字段 ${name}`);
    }
    if (schema.additionalProperties === false) {
      for (const name of Object.keys(record)) {
        if (!(name in properties)) errors.push(`${path}: 未知字段 ${name}`);
      }
    }
    for (const [name, child] of Object.entries(properties)) {
      if (name in record) {
        errors.push(...validateJsonSchema(record[name], child, `${path}.${name}`));
      }
    }
  }

  return errors;
}

export async function loadSchema(name: string): Promise<JsonSchema> {
  const text = await readFile(new URL(`../schemas/${name}`, import.meta.url), "utf8");
  return JSON.parse(text) as JsonSchema;
}
